"""Chat-роуты с памятью, эмоциями, контекст-агрегатором и SSE-стримом (PR 4.5)."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends
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


async def _maybe_extract_facts(user_id: str, history: list[dict]) -> None:
    """Периодически достаёт факты из истории и кладёт их в долгосрочную память."""
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
        logger.info("📝 Extracted %d facts for user=%s", len(facts), user_id)
    except Exception as exc:  # pragma: no cover - не валим основной поток
        logger.warning("fact extraction failed: %s", exc)


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
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ChatResponseOut:
    convos = ConversationRepository(session)
    await convos.add(user.user_id, "user", body.message)

    emotion_service = EmotionService(default_router())
    aggregator = ContextAggregator(session, emotion_service=emotion_service)
    full_ctx = await aggregator.get_full_context(user.user_id, body.message)

    # Сохраняем эмоцию в историю
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

    history_rows = full_ctx.history[:-0] if False else full_ctx.history[:-1] if full_ctx.history else []
    messages = _ctx_messages(BASE_SYSTEM, full_ctx, history_rows, body.message)
    response = await default_router().chat(messages, profile=body.profile)  # type: ignore[arg-type]
    await convos.add(user.user_id, "assistant", response.text)

    if body.use_memory:
        try:
            await default_memory().add(
                [
                    MemoryRecord(
                        id="",
                        text=body.message,
                        user_id=user.user_id,
                        metadata={"role": "user"},
                    ),
                    MemoryRecord(
                        id="",
                        text=response.text,
                        user_id=user.user_id,
                        metadata={"role": "assistant"},
                    ),
                ]
            )
        except Exception:
            pass

    # Авто-извлечение фактов раз в FACT_EXTRACT_EVERY сообщений
    await _maybe_extract_facts(user.user_id, full_ctx.history + [{"role": "user", "content": body.message}])

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

    async def event_source() -> AsyncIterator[bytes]:
        collected: list[str] = []
        try:
            async for chunk in default_router().stream(messages, profile=body.profile):  # type: ignore[arg-type]
                collected.append(chunk)
                yield f"data: {chunk}\n\n".encode()
            yield b"event: done\ndata: end\n\n"
        finally:
            full = "".join(collected)
            if full:
                await ConversationRepository(session).add(user.user_id, "assistant", full)
                await session.commit()
                if body.use_memory:
                    try:
                        await default_memory().add(
                            [
                                MemoryRecord(id="", text=body.message, user_id=user.user_id),
                                MemoryRecord(id="", text=full, user_id=user.user_id),
                            ]
                        )
                    except Exception:
                        pass
                await _maybe_extract_facts(
                    user.user_id,
                    full_ctx.history + [{"role": "user", "content": body.message}],
                )

    return StreamingResponse(event_source(), media_type="text/event-stream")
