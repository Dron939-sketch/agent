"""Chat-роуты с памятью, эмоциями, контекст-агрегатором и SSE-стримом."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthenticatedUser
from app.core.logging import get_logger
from app.db import ConversationRepository, EmotionRepository
from app.services import ChatMessage, default_router
from app.services.context import ContextAggregator
from app.services.emotion import EmotionService
from app.services.memory import MemoryRecord, default_memory
from app.services.memory.extractor import extract_facts

from .deps import get_current_user, get_session

logger = get_logger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])

BASE_SYSTEM = (
    "Ты Фреди, дружелюбный и всемогущий AI-помощник. Отвечай по-русски, "
    "обращайся на «ты», будь полезным и эмпатичным. "
    "Учитывай эмоциональное состояние и память пользователя."
)

# Каждые N сообщений запускаем авто-извлечение фактов
FACT_EXTRACT_EVERY = 6


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    profile: str = Field(default="smart")
    use_memory: bool = True


class ChatMessageOut(BaseModel):
    role: str
    content: str


class ChatResponseOut(BaseModel):
    reply: str
    model: str
    emotion: str | None = None
    tone: str | None = None
    recalled: list[str] = Field(default_factory=list)


def _ctx_messages(
    base_system: str,
    aggregator_ctx,  # type: ignore[no-untyped-def]
    history: list[dict],
    user_message: str,
) -> list[ChatMessage]:
    system_text = ContextAggregator.format_for_prompt(aggregator_ctx, base_system)
    msgs: list[ChatMessage] = [ChatMessage(role="system", content=system_text)]
    for m in history:
        msgs.append(ChatMessage(role=m["role"], content=m["content"]))  # type: ignore[arg-type]
    msgs.append(ChatMessage(role="user", content=user_message))
    return msgs


async def _extract_facts_bg(user_id: str, history: list[dict]) -> None:
    if not history or len(history) % FACT_EXTRACT_EVERY != 0:
        return
    try:
        facts = await extract_facts(default_router(), history[-FACT_EXTRACT_EVERY:])
        if not facts:
            return
        await default_memory().add(
            [
                MemoryRecord(
                    id="",
                    text=f.fact,
                    user_id=user_id,
                    metadata={"kind": "fact", "type": f.type, "importance": f.importance},
                )
                for f in facts
            ]
        )
        logger.info("📝 Extracted %d facts (bg) for user=%s", len(facts), user_id)
    except Exception as exc:  # pragma: no cover
        logger.warning("background fact extraction failed: %s", exc)


async def _store_chat_memory(user_id: str, user_msg: str, assistant_msg: str) -> None:
    try:
        await default_memory().add(
            [
                MemoryRecord(id="", text=user_msg, user_id=user_id, metadata={"role": "user"}),
                MemoryRecord(
                    id="", text=assistant_msg, user_id=user_id, metadata={"role": "assistant"}
                ),
            ]
        )
    except Exception as exc:
        logger.warning("background memory store failed: %s", exc)


@router.get("/history", response_model=list[ChatMessageOut])
async def history(
    limit: int = 50,
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[ChatMessageOut]:
    rows = await ConversationRepository(session).history(user.user_id, limit=limit)
    return [ChatMessageOut(role=r["role"], content=r["content"]) for r in rows]


@router.post("/", response_model=ChatResponseOut)
async def send(
    body: ChatRequest,
    background: BackgroundTasks,
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ChatResponseOut:
    convos = ConversationRepository(session)
    await convos.add(user.user_id, "user", body.message)

    emotion_service = EmotionService(default_router())
    aggregator = ContextAggregator(session, emotion_service=emotion_service)
    full_ctx = await aggregator.get_full_context(user.user_id, body.message)

    if full_ctx.emotion:
        try:
            await EmotionRepository(session).add(
                user_id=user.user_id,
                primary=full_ctx.emotion.primary,
                intensity=full_ctx.emotion.intensity,
                confidence=full_ctx.emotion.confidence,
                tone=full_ctx.emotion.tone,
                needs_support=full_ctx.emotion.needs_support,
            )
        except Exception as exc:
            logger.warning("emotion log failed: %s", exc)

    history_rows = full_ctx.history[:-1] if full_ctx.history else []
    messages = _ctx_messages(BASE_SYSTEM, full_ctx, history_rows, body.message)

    response = await default_router().chat(messages, profile=body.profile)  # type: ignore[arg-type]
    await convos.add(user.user_id, "assistant", response.text)

    if body.use_memory:
        background.add_task(_store_chat_memory, user.user_id, body.message, response.text)
    background.add_task(
        _extract_facts_bg,
        user.user_id,
        full_ctx.history + [{"role": "user", "content": body.message}],
    )

    return ChatResponseOut(
        reply=response.text,
        model=response.model,
        emotion=full_ctx.emotion.primary if full_ctx.emotion else None,
        tone=full_ctx.emotion.tone if full_ctx.emotion else None,
        recalled=full_ctx.recalled,
    )


@router.post("/stream")
async def stream(
    body: ChatRequest,
    background: BackgroundTasks,
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    convos = ConversationRepository(session)
    await convos.add(user.user_id, "user", body.message)

    emotion_service = EmotionService(default_router())
    aggregator = ContextAggregator(session, emotion_service=emotion_service)
    full_ctx = await aggregator.get_full_context(user.user_id, body.message)

    if full_ctx.emotion:
        try:
            await EmotionRepository(session).add(
                user_id=user.user_id,
                primary=full_ctx.emotion.primary,
                intensity=full_ctx.emotion.intensity,
                confidence=full_ctx.emotion.confidence,
                tone=full_ctx.emotion.tone,
                needs_support=full_ctx.emotion.needs_support,
            )
        except Exception as exc:
            logger.warning("emotion log failed: %s", exc)

    history_rows = full_ctx.history[:-1] if full_ctx.history else []
    messages = _ctx_messages(BASE_SYSTEM, full_ctx, history_rows, body.message)
    history_snapshot = list(full_ctx.history)
    user_message = body.message
    profile = body.profile
    use_memory = body.use_memory
    user_id = user.user_id

    async def event_source() -> AsyncIterator[bytes]:
        collected: list[str] = []
        try:
            async for chunk in default_router().stream(messages, profile=profile):  # type: ignore[arg-type]
                collected.append(chunk)
                # Кодируем чанк как JSON, чтобы пробелы и переводы строк
                # передавались БУКВАЛЬНО, не теряясь в SSE-парсере.
                payload = json.dumps({"t": chunk}, ensure_ascii=False)
                yield f"data: {payload}\n\n".encode("utf-8")
            yield b"event: done\ndata: end\n\n"
        finally:
            full = "".join(collected)
            if full:
                from app.db import session_scope

                try:
                    async with session_scope() as s2:
                        await ConversationRepository(s2).add(user_id, "assistant", full)
                except Exception as exc:
                    logger.warning("stream save failed: %s", exc)

                if use_memory:
                    try:
                        await _store_chat_memory(user_id, user_message, full)
                    except Exception:
                        pass
                try:
                    await _extract_facts_bg(
                        user_id,
                        history_snapshot + [{"role": "user", "content": user_message}],
                    )
                except Exception:
                    pass

    return StreamingResponse(event_source(), media_type="text/event-stream")
