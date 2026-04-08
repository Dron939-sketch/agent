"""Chat-роуты с памятью, эмоциями, intents, KB, tool-use, sentence-streaming."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthenticatedUser
from app.core.config import Config
from app.core.logging import get_logger
from app.db import ConversationRepository, EmotionRepository
from app.services import ChatMessage, default_router
from app.services.context import ContextAggregator
from app.services.emotion import EmotionService
from app.services.intents import detect_intent
from app.services.knowledge import freddy_persona
from app.services.llm.sentences import SentenceBuffer
from app.services.llm.tooluse import ToolUseChat
from app.services.memory import MemoryRecord, default_memory
from app.services.memory.extractor import extract_facts

from .deps import get_current_user, get_session

logger = get_logger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])


def _base_system() -> str:
    persona = freddy_persona()
    if persona:
        return persona
    return (
        "Ты Фреди, дружелюбный и всемогущий AI-помощник. Отвечай по-русски, "
        "обращайся на «ты», будь полезным и эмпатичным."
    )


FACT_EXTRACT_EVERY = 6


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    profile: str = Field(default="smart")
    use_memory: bool = True
    use_tools: bool = True


class ChatMessageOut(BaseModel):
    id: int | None = None
    role: str
    content: str


class ChatResponseOut(BaseModel):
    reply: str
    model: str
    emotion: str | None = None
    tone: str | None = None
    recalled: list[str] = Field(default_factory=list)
    intent: str | None = None
    message_id: int | None = None
    used_tools: bool = False


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


async def _handle_intent(user_id: str, intent_type: str, payload: str) -> str | None:
    store = default_memory()
    if intent_type == "forget":
        if not payload:
            return "Что именно забыть? Скажи, например: «забудь, что я люблю кофе»."
        try:
            removed = await store.forget(user_id, payload)
            if removed:
                return f"Готово, удалил {removed} запис(и) про «{payload}»."
            return f"В памяти ничего такого не нашёл — {payload}."
        except Exception as exc:
            logger.warning("forget failed: %s", exc)
            return "Не получилось забыть, попробуй ещё раз."
    if intent_type == "remember":
        if not payload:
            return "Что запомнить? Скажи: «запомни, что я работаю на Python»."
        try:
            await store.add(
                [
                    MemoryRecord(
                        id="",
                        text=payload,
                        user_id=user_id,
                        metadata={"kind": "fact", "source": "explicit"},
                    )
                ]
            )
            return f"Запомнил: «{payload}»."
        except Exception as exc:
            logger.warning("remember failed: %s", exc)
            return "Не получилось запомнить, попробуй ещё раз."
    if intent_type == "list_memory":
        try:
            hits = await store.search("важное о пользователе", user_id=user_id, top_k=10)
            if not hits:
                return "Пока ничего не помню. Расскажи о себе — запомню важное."
            top = "\n".join(f"• {h.text}" for h in hits[:8])
            return f"Вот что я помню:\n{top}"
        except Exception as exc:
            logger.warning("list_memory failed: %s", exc)
            return "Не смог достать память."
    return None


async def _try_tool_use_chat(
    system_text: str,
    history_rows: list[dict],
    user_message: str,
) -> tuple[str | None, bool]:
    if not Config.ANTHROPIC_API_KEY:
        return None, False

    tool_chat = ToolUseChat()
    if not tool_chat.is_available():
        return None, False

    msgs: list[dict] = []
    for m in history_rows:
        if m["role"] in ("user", "assistant"):
            msgs.append({"role": m["role"], "content": m["content"]})
    msgs.append({"role": "user", "content": user_message})

    try:
        reply = await tool_chat.chat(system_text, msgs, max_tokens=1500, temperature=0.7)
    except Exception as exc:
        logger.warning("tool-use chat failed: %s", exc)
        return None, False

    return (reply, True) if reply else (None, False)


@router.get("/history", response_model=list[ChatMessageOut])
async def history(
    limit: int = 50,
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[ChatMessageOut]:
    rows = await ConversationRepository(session).history(user.user_id, limit=limit)
    return [ChatMessageOut(id=r.get("id"), role=r["role"], content=r["content"]) for r in rows]


@router.post("/", response_model=ChatResponseOut)
async def send(
    body: ChatRequest,
    background: BackgroundTasks,
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ChatResponseOut:
    convos = ConversationRepository(session)
    await convos.add(user.user_id, "user", body.message)

    intent = detect_intent(body.message)
    if intent.type != "none":
        intent_reply = await _handle_intent(user.user_id, intent.type, intent.payload)
        if intent_reply:
            msg_id = await convos.add(user.user_id, "assistant", intent_reply)
            return ChatResponseOut(
                reply=intent_reply,
                model="intent-handler",
                intent=intent.type,
                message_id=msg_id,
            )

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
    system_text = ContextAggregator.format_for_prompt(full_ctx, _base_system())

    used_tools = False
    response_text: str | None = None
    response_model = "router"

    if body.profile == "smart" and body.use_tools:
        response_text, used_tools = await _try_tool_use_chat(
            system_text, history_rows, body.message
        )
        if response_text:
            response_model = "claude-sonnet-4-6+tools"

    if not response_text:
        messages = _ctx_messages(_base_system(), full_ctx, history_rows, body.message)
        router_response = await default_router().chat(messages, profile=body.profile)  # type: ignore[arg-type]
        response_text = router_response.text
        response_model = router_response.model

    msg_id = await convos.add(user.user_id, "assistant", response_text)

    if body.use_memory:
        background.add_task(_store_chat_memory, user.user_id, body.message, response_text)
    background.add_task(
        _extract_facts_bg,
        user.user_id,
        full_ctx.history + [{"role": "user", "content": body.message}],
    )

    return ChatResponseOut(
        reply=response_text,
        model=response_model,
        emotion=full_ctx.emotion.primary if full_ctx.emotion else None,
        tone=full_ctx.emotion.tone if full_ctx.emotion else None,
        recalled=full_ctx.recalled,
        message_id=msg_id,
        used_tools=used_tools,
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

    intent = detect_intent(body.message)
    intent_reply: str | None = None
    if intent.type != "none":
        intent_reply = await _handle_intent(user.user_id, intent.type, intent.payload)

    if intent_reply is None:
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
        messages = _ctx_messages(_base_system(), full_ctx, history_rows, body.message)
        history_snapshot = list(full_ctx.history)
    else:
        history_snapshot = []

    user_message = body.message
    profile = body.profile
    use_memory = body.use_memory
    user_id = user.user_id

    async def event_source() -> AsyncIterator[bytes]:
        if intent_reply is not None:
            payload = json.dumps({"t": intent_reply}, ensure_ascii=False)
            yield f"data: {payload}\n\n".encode("utf-8")
            # Также отдаём sentence-event для TTS
            sentence_payload = json.dumps({"s": intent_reply}, ensure_ascii=False)
            yield f"data: {sentence_payload}\n\n".encode("utf-8")
            yield b"event: done\ndata: end\n\n"
            from app.db import session_scope

            try:
                async with session_scope() as s2:
                    await ConversationRepository(s2).add(user_id, "assistant", intent_reply)
            except Exception as exc:
                logger.warning("intent save failed: %s", exc)
            return

        # Sprint 5: эмитим И токены (для UI), И готовые предложения (для TTS).
        # Фронт собирает токены в bubble и параллельно играет TTS по sentence.
        collected: list[str] = []
        sentence_buf = SentenceBuffer()

        try:
            async for chunk in default_router().stream(messages, profile=profile):  # type: ignore[arg-type]
                collected.append(chunk)
                # token event — для UI
                token_payload = json.dumps({"t": chunk}, ensure_ascii=False)
                yield f"data: {token_payload}\n\n".encode("utf-8")
                # sentence event — для TTS
                for sentence in sentence_buf.add(chunk):
                    sent_payload = json.dumps({"s": sentence}, ensure_ascii=False)
                    yield f"data: {sent_payload}\n\n".encode("utf-8")

            tail = sentence_buf.flush()
            if tail:
                sent_payload = json.dumps({"s": tail}, ensure_ascii=False)
                yield f"data: {sent_payload}\n\n".encode("utf-8")

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
