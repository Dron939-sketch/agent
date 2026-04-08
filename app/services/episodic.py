"""Episodic memory summarizer (ROUND 3).

Превращает закрытую сессию диалога в короткое «эпизодическое воспоминание»:
заголовок + 2-4 предложения саммари. В будущем это читается в system prompt
как «раньше мы обсуждали…».

Алгоритм:
1. Берём сообщения сессии.
2. Пытаемся сгенерировать саммари через LLM router (профиль ``fast``).
3. Если LLM недоступен — откатываемся к экстрактивному саммари:
   первые несколько user-реплик, обрезанные до разумной длины.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.logging import get_logger
from app.db import ChatSession, session_scope
from app.db.chat_session_repo import ChatSessionRepository
from app.services.llm import ChatMessage, LLMError, default_router

logger = get_logger(__name__)


SUMMARY_SYSTEM_PROMPT = (
    "Ты помощник-саммаризатор. На входе — диалог Фреди с пользователем. "
    "Твоя задача:\n"
    "1. В первой строке дай короткий (до 40 символов) заголовок на русском.\n"
    "2. Затем с новой строки — 2-4 предложения саммари: о чём говорили, "
    "какие решения приняты, какие вопросы остались открытыми.\n"
    "Формат ответа:\n"
    "TITLE: <заголовок>\n"
    "SUMMARY: <саммари>"
)

MIN_MESSAGES_FOR_SUMMARY = 2
MAX_TITLE_LEN = 80
MAX_SUMMARY_LEN = 500


@dataclass(slots=True)
class EpisodicSummary:
    title: str
    summary: str


def _extractive_fallback(messages: list[dict]) -> EpisodicSummary:
    """Простой экстрактивный саммари без LLM."""
    user_msgs = [m["content"].strip() for m in messages if m.get("role") == "user"]
    if not user_msgs:
        return EpisodicSummary(title="Короткий диалог", summary="Диалог без сообщений от пользователя.")

    first = user_msgs[0][:60].strip()
    title = first if first else "Диалог"
    if len(title) == 60 and len(user_msgs[0]) > 60:
        title = title.rstrip() + "…"

    topics = user_msgs[:3]
    joined = " / ".join(t[:120] for t in topics)
    summary = f"Пользователь писал: {joined}. Всего сообщений пользователя: {len(user_msgs)}."
    return EpisodicSummary(title=title[:MAX_TITLE_LEN], summary=summary[:MAX_SUMMARY_LEN])


def _parse_llm_output(text: str, messages: list[dict]) -> EpisodicSummary:
    """Парсит ``TITLE: … / SUMMARY: …`` формат."""
    title = ""
    summary = ""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.upper().startswith("TITLE:"):
            title = stripped.split(":", 1)[1].strip()
        elif stripped.upper().startswith("SUMMARY:"):
            summary = stripped.split(":", 1)[1].strip()
        elif summary and stripped:
            summary += " " + stripped

    if not title or not summary:
        # LLM проигнорировал формат — берём текст as-is, но отделяем заголовок
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        if lines:
            title = title or lines[0][:MAX_TITLE_LEN]
            summary = summary or " ".join(lines[1:]) or lines[0]

    if not summary:
        return _extractive_fallback(messages)

    return EpisodicSummary(
        title=title[:MAX_TITLE_LEN] or "Диалог",
        summary=summary[:MAX_SUMMARY_LEN],
    )


def _format_dialogue(messages: list[dict]) -> str:
    """Превращает сообщения в компактный текст для LLM."""
    lines: list[str] = []
    for m in messages:
        role = m.get("role", "")
        content = (m.get("content") or "").strip().replace("\n", " ")
        if not content:
            continue
        prefix = "Пользователь" if role == "user" else "Фреди"
        lines.append(f"{prefix}: {content[:400]}")
    return "\n".join(lines)


async def summarize_dialogue(messages: list[dict]) -> EpisodicSummary:
    """Основная функция: пытается LLM, откатывается на экстрактив."""
    if len(messages) < MIN_MESSAGES_FOR_SUMMARY:
        return _extractive_fallback(messages)

    dialogue = _format_dialogue(messages)
    if not dialogue:
        return _extractive_fallback(messages)

    try:
        router = default_router()
        response = await router.chat(
            [
                ChatMessage(role="system", content=SUMMARY_SYSTEM_PROMPT),
                ChatMessage(role="user", content=dialogue),
            ],
            profile="fast",
            temperature=0.3,
            max_tokens=300,
        )
    except LLMError as exc:
        logger.info("episodic LLM summary failed, using extractive: %s", exc)
        return _extractive_fallback(messages)
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning("episodic summary exception: %s", exc)
        return _extractive_fallback(messages)

    text = (response.text or "").strip()
    if not text:
        return _extractive_fallback(messages)
    return _parse_llm_output(text, messages)


async def summarize_session(session_id: int) -> EpisodicSummary | None:
    """Загружает сессию из БД, суммаризует и сохраняет summary."""
    async with session_scope() as session:
        repo = ChatSessionRepository(session)
        chat_session = await repo.get(session_id)
        if chat_session is None or chat_session.summary is not None:
            return None  # уже закрыта или нет такой

        raw_messages = await repo.messages(session_id)
        dialog = [
            {"role": m.role, "content": m.content} for m in raw_messages
        ]

    summary = await summarize_dialogue(dialog)

    async with session_scope() as session:
        repo = ChatSessionRepository(session)
        await repo.save_summary(session_id, title=summary.title, summary=summary.summary)

    logger.info(
        "📖 episodic summary saved: session=%d title=%r", session_id, summary.title
    )
    return summary
