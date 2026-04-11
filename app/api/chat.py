"""Chat-роуты с памятью, эмоциями, intents (memory + coach), KB, tool-use, sentence-streaming.

OPTIMIZED: profile=fast + use_tools=false skips heavy context aggregation for speed.
"""

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
from app.db import (
    ChatSessionRepository,
    ConversationRepository,
    EmotionRepository,
    GoalRepository,
    HabitRepository,
)
from app.services.episodic import summarize_session
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
    aggregator_ctx,
    history: list[dict],
    user_message: str,
) -> list[ChatMessage]:
    system_text = ContextAggregator.format_for_prompt(aggregator_ctx, base_system)
    msgs: list[ChatMessage] = [ChatMessage(role="system", content=system_text)]
    for m in history:
        msgs.append(ChatMessage(role=m["role"], content=m["content"]))
    msgs.append(ChatMessage(role="user", content=user_message))
    return msgs


def _simple_messages(
    system: str,
    history: list[dict],
    user_message: str,
) -> list[ChatMessage]:
    """Lightweight message builder without full context aggregation."""
    msgs: list[ChatMessage] = [ChatMessage(role="system", content=system)]
    for m in history[-10:]:
        msgs.append(ChatMessage(role=m["role"], content=m["content"]))
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
        logger.info("Extracted %d facts (bg) for user=%s", len(facts), user_id)
    except Exception as exc:
        logger.warning("background fact extraction failed: %s", exc)

    try:
        from app.services.memory.knowledge_graph import auto_profile_after_dialogue
        result = await auto_profile_after_dialogue(user_id, history[-FACT_EXTRACT_EVERY:])
        if result.get("stored", 0) > 0:
            logger.info("Knowledge graph: +%d triples for user=%s", result["stored"], user_id)
    except Exception as exc:
        logger.warning("knowledge graph extraction failed: %s", exc)


async def _store_chat_memory(user_id: str, user_msg: str, assistant_msg: str) -> None:
    try:
        await default_memory().add(
            [
                MemoryRecord(id="", text=user_msg, user_id=user_id, metadata={"role": "user"}),
                MemoryRecord(id="", text=assistant_msg, user_id=user_id, metadata={"role": "assistant"}),
            ]
        )
    except Exception as exc:
        logger.warning("background memory store failed: %s", exc)


async def _handle_intent(
    session: AsyncSession,
    user_id: str,
    intent_type: str,
    payload: str,
) -> str | None:
    store = default_memory()

    if intent_type == "forget":
        if not payload:
            return "Что именно забыть?"
        try:
            removed = await store.forget(user_id, payload)
            return f"Готово, удалил {removed} запис(и) про «{payload}»." if removed else f"Не нашёл — {payload}."
        except Exception:
            return "Не получилось забыть."

    if intent_type == "remember":
        if not payload:
            return "Что запомнить?"
        try:
            await store.add([MemoryRecord(id="", text=payload, user_id=user_id, metadata={"kind": "fact", "source": "explicit"})])
            return f"Запомнил: «{payload}»."
        except Exception:
            return "Не получилось запомнить."

    if intent_type == "list_memory":
        try:
            hits = await store.search("важное о пользователе", user_id=user_id, top_k=10)
            if not hits:
                return "Пока ничего не помню."
            return "Вот что я помню:\n" + "\n".join(f"• {h.text}" for h in hits[:8])
        except Exception:
            return "Не смог достать память."

    if intent_type == "goal_set":
        if not payload:
            return "Какая цель?"
        try:
            goal_id = await GoalRepository(session).add(user_id, payload)
            return f"Записал цель: «{payload}». (#G{goal_id})"
        except Exception:
            return "Не получилось записать цель."

    if intent_type == "goal_list":
        try:
            goals = await GoalRepository(session).list_active(user_id)
            if not goals:
                return "Нет активных целей."
            return "Цели:\n" + "\n".join(f"• #{g.id} — {g.title} ({g.progress_pct}%)" for g in goals[:10])
        except Exception:
            return "Не смог достать цели."

    if intent_type == "habit_create":
        if not payload:
            return "Какая привычка?"
        try:
            await HabitRepository(session).add(user_id, payload)
            return f"Привычка «{payload}» добавлена."
        except Exception:
            return "Не получилось добавить привычку."

    if intent_type == "habit_check":
        if not payload:
            return "Какую привычку отметить?"
        try:
            repo = HabitRepository(session)
            habit = await repo.find_by_title(user_id, payload)
            if not habit:
                return f"Не нашёл привычку «{payload}»."
            result = await repo.check_in(habit.id, user_id)
            if result["was_already_done_today"]:
                return f"Уже отмечено. Streak: {result['streak']}"
            return f"Отметил «{habit.title}». Streak: {result['streak']}"
        except Exception:
            return "Не получилось отметить."

    if intent_type == "habit_list":
        try:
            repo = HabitRepository(session)
            await repo.reset_broken_streaks(user_id)
            habits = await repo.list(user_id)
            if not habits:
                return "Нет привычек."
            return "Привычки:\n" + "\n".join(f"• {h.title} (streak: {h.streak})" for h in habits[:10])
        except Exception:
            return "Не смог достать привычки."

    if intent_type == "remind":
        if not payload:
            return "О чём напомнить?"
        try:
            from app.services.tasks import get_reminder_manager
            result = await get_reminder_manager().create_from_text(user_id, payload, tz_offset=3)
            return f"Напомню: «{result.get('title', payload)}» — {_format_dt(result.get('scheduled_at', ''))}."
        except ValueError:
            return "Не смог разобрать время."
        except Exception:
            return "Не получилось создать напоминание."

    if intent_type == "task_create":
        if not payload:
            return "Какую задачу добавить?"
        try:
            from app.services.tasks import get_reminder_manager
            result = await get_reminder_manager().create_from_text(user_id, payload, tz_offset=3)
            return f"Задача «{result.get('title', payload)}» добавлена."
        except Exception:
            return "Не получилось добавить задачу."

    if intent_type == "task_list":
        try:
            from app.services.tasks import get_reminder_manager
            reminders = await get_reminder_manager().list_pending(user_id)
            if not reminders:
                return "Нет активных напоминаний."
            return "Напоминания:\n" + "\n".join(f"• #{r['id']} — {r['title']}" for r in reminders[:10])
        except Exception:
            return "Не смог достать задачи."

    return None


def _format_dt(iso_str: str) -> str:
    if not iso_str:
        return "скоро"
    try:
        from datetime import datetime, timedelta, timezone as tz
        dt = datetime.fromisoformat(iso_str)
        local = dt.replace(tzinfo=tz.utc).astimezone(tz(timedelta(hours=3)))
        now = datetime.now(tz(timedelta(hours=3)))
        delta = local - now
        if delta.days == 0:
            return f"сегодня в {local.strftime('%H:%M')}"
        if delta.days == 1:
            return f"завтра в {local.strftime('%H:%M')}"
        return f"{local.strftime('%d.%m')} в {local.strftime('%H:%M')}"
    except Exception:
        return iso_str


async def _attach_chat_session(
    session: AsyncSession, user_id: str, background: BackgroundTasks
) -> int:
    repo = ChatSessionRepository(session)
    try:
        active_id, stale_id = await repo.get_or_create_active(user_id)
    except Exception as exc:
        logger.warning("chat session attach failed: %s", exc)
        return 0
    if stale_id is not None:
        background.add_task(summarize_session, stale_id)
    return active_id


async def _try_tool_use_chat(
    system_text: str,
    history_rows: list[dict],
    user_message: str,
    user_id: str = "",
) -> tuple[str | None, bool]:
    if not Config.ANTHROPIC_API_KEY:
        return None, False
    tool_chat = ToolUseChat()
    if not tool_chat.is_available():
        return None, False
    msgs = [{"role": m["role"], "content": m["content"]} for m in history_rows if m["role"] in ("user", "assistant")]
    msgs.append({"role": "user", "content": user_message})
    try:
        reply = await tool_chat.chat(system_text, msgs, max_tokens=1500, temperature=0.7, user_id=user_id)
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
    import time
    start = time.time()

    convos = ConversationRepository(session)
    chat_session_id = await _attach_chat_session(session, user.user_id, background)
    await convos.add(user.user_id, "user", body.message, chat_session_id=chat_session_id or None)

    # Intent detection (fast, local)
    intent = detect_intent(body.message)
    if intent.type != "none":
        intent_reply = await _handle_intent(session, user.user_id, intent.type, intent.payload)
        if intent_reply:
            msg_id = await convos.add(user.user_id, "assistant", intent_reply, chat_session_id=chat_session_id or None)
            if chat_session_id:
                try:
                    await ChatSessionRepository(session).touch(chat_session_id)
                except Exception:
                    pass
            elapsed = time.time() - start
            logger.info("chat intent=%s, %.1fs", intent.type, elapsed)
            return ChatResponseOut(reply=intent_reply, model="intent-handler", intent=intent.type, message_id=msg_id)

    # Chain detection
    try:
        from app.services.chains import is_chain_request, plan_chain, execute_chain, format_chain_response
        if is_chain_request(body.message):
            plan = await plan_chain(body.message)
            if plan and plan.get("steps"):
                results = await execute_chain(plan)
                chain_reply = format_chain_response(plan, results)
                msg_id = await convos.add(user.user_id, "assistant", chain_reply)
                elapsed = time.time() - start
                logger.info("chat chain, %.1fs", elapsed)
                return ChatResponseOut(reply=chain_reply, model="chain-executor", message_id=msg_id)
    except Exception as exc:
        logger.warning("chain execution failed: %s", exc)

    # ========================================================
    # FAST PATH: skip heavy context for profile=fast + no tools
    # Used by Frederick basic mode for speed
    # ========================================================
    is_fast_path = body.profile == "fast" and not body.use_tools

    if is_fast_path:
        # Lightweight: just get recent history, no emotions/memory/KB
        history_rows = await convos.history(user.user_id, limit=10)
        messages = _simple_messages(_base_system(), history_rows, body.message)
        router_response = await default_router().chat(messages, profile="fast")
        response_text = router_response.text
        response_model = router_response.model

        msg_id = await convos.add(user.user_id, "assistant", response_text, chat_session_id=chat_session_id or None)
        if chat_session_id:
            try:
                await ChatSessionRepository(session).touch(chat_session_id)
            except Exception:
                pass

        # Store memory in background (non-blocking)
        if body.use_memory:
            background.add_task(_store_chat_memory, user.user_id, body.message, response_text)

        elapsed = time.time() - start
        logger.info("chat fast-path model=%s, %.1fs", response_model, elapsed)
        return ChatResponseOut(reply=response_text, model=response_model, message_id=msg_id)

    # ========================================================
    # FULL PATH: emotions, memory, KB, tools
    # ========================================================
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
        response_text, used_tools = await _try_tool_use_chat(system_text, history_rows, body.message, user_id=user.user_id)
        if response_text:
            response_model = "claude-sonnet-4-6+tools"

    if not response_text:
        messages = _ctx_messages(_base_system(), full_ctx, history_rows, body.message)
        router_response = await default_router().chat(messages, profile=body.profile)
        response_text = router_response.text
        response_model = router_response.model

    msg_id = await convos.add(user.user_id, "assistant", response_text, chat_session_id=chat_session_id or None)
    if chat_session_id:
        try:
            await ChatSessionRepository(session).touch(chat_session_id)
        except Exception:
            pass

    if body.use_memory:
        background.add_task(_store_chat_memory, user.user_id, body.message, response_text)
    background.add_task(
        _extract_facts_bg,
        user.user_id,
        full_ctx.history + [{"role": "user", "content": body.message}],
    )

    elapsed = time.time() - start
    logger.info("chat full-path model=%s, tools=%s, %.1fs", response_model, used_tools, elapsed)
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
    chat_session_id = await _attach_chat_session(session, user.user_id, background)
    await convos.add(user.user_id, "user", body.message, chat_session_id=chat_session_id or None)

    intent = detect_intent(body.message)
    intent_reply: str | None = None
    if intent.type != "none":
        intent_reply = await _handle_intent(session, user.user_id, intent.type, intent.payload)

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
            except Exception:
                pass

        history_rows = full_ctx.history[:-1] if full_ctx.history else []
        messages = _ctx_messages(_base_system(), full_ctx, history_rows, body.message)
        history_snapshot = list(full_ctx.history)
    else:
        history_snapshot = []

    user_message = body.message
    profile = body.profile
    use_memory = body.use_memory
    user_id = user.user_id
    cs_id = chat_session_id or None

    async def event_source() -> AsyncIterator[bytes]:
        if intent_reply is not None:
            payload = json.dumps({"t": intent_reply}, ensure_ascii=False)
            yield f"data: {payload}\n\n".encode("utf-8")
            sentence_payload = json.dumps({"s": intent_reply}, ensure_ascii=False)
            yield f"data: {sentence_payload}\n\n".encode("utf-8")
            yield b"event: done\ndata: end\n\n"
            from app.db import session_scope
            try:
                async with session_scope() as s2:
                    await ConversationRepository(s2).add(user_id, "assistant", intent_reply, chat_session_id=cs_id)
                    if cs_id:
                        await ChatSessionRepository(s2).touch(cs_id)
            except Exception:
                pass
            return

        collected: list[str] = []
        sentence_buf = SentenceBuffer()
        try:
            async for chunk in default_router().stream(messages, profile=profile):
                collected.append(chunk)
                yield f"data: {json.dumps({'t': chunk}, ensure_ascii=False)}\n\n".encode("utf-8")
                for sentence in sentence_buf.add(chunk):
                    yield f"data: {json.dumps({'s': sentence}, ensure_ascii=False)}\n\n".encode("utf-8")

            tail = sentence_buf.flush()
            if tail:
                yield f"data: {json.dumps({'s': tail}, ensure_ascii=False)}\n\n".encode("utf-8")
            yield b"event: done\ndata: end\n\n"
        finally:
            full = "".join(collected)
            if full:
                from app.db import session_scope
                try:
                    async with session_scope() as s2:
                        await ConversationRepository(s2).add(user_id, "assistant", full, chat_session_id=cs_id)
                        if cs_id:
                            await ChatSessionRepository(s2).touch(cs_id)
                except Exception:
                    pass
                if use_memory:
                    try:
                        await _store_chat_memory(user_id, user_message, full)
                    except Exception:
                        pass

    return StreamingResponse(event_source(), media_type="text/event-stream")
