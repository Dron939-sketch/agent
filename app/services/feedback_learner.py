"""Feedback learner — превращает лайки/дизлайки в уроки для будущих ответов.

ROUND 2: Self-improvement from feedback.

Идея: когда пользователь дизлайкает ответ, мы сохраняем «анти-паттерн» —
короткую заметку «на вопрос X ответ в стиле Y не понравился». В будущем эта
заметка включается в системный промпт как подсказка «избегай такого».

Лайки тоже сохраняются как «позитивные примеры». Обе формы попадают в
`fr_memories` с `kind="lesson"` и метаданными `{"score": ±1}`.
"""

from __future__ import annotations

from app.core.logging import get_logger
from app.db import ConversationRepository, session_scope
from app.services.memory import MemoryRecord, default_memory

logger = get_logger(__name__)


MAX_SNIPPET = 160  # обрезаем длинные реплики, чтобы урок читался быстро
LESSON_LIMIT_PER_USER = 30  # сколько уроков максимально держим на пользователя


def _truncate(text: str, limit: int = MAX_SNIPPET) -> str:
    text = (text or "").strip().replace("\n", " ")
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _format_lesson(
    *, score: int, user_msg: str, assistant_msg: str, note: str | None
) -> str:
    user_snip = _truncate(user_msg)
    asst_snip = _truncate(assistant_msg)
    if score < 0:
        core = (
            f"❌ АНТИ-ПАТТЕРН: на сообщение «{user_snip}» "
            f"ответ «{asst_snip}» пользователю НЕ понравился."
        )
    elif score > 0:
        core = (
            f"✅ ХОРОШИЙ ПРИМЕР: на сообщение «{user_snip}» "
            f"ответ «{asst_snip}» пользователю понравился."
        )
    else:
        core = (
            f"➖ НЕЙТРАЛЬНО: на «{user_snip}» был ответ «{asst_snip}»."
        )
    if note:
        core += f" Комментарий: {_truncate(note, 120)}"
    return core


async def _load_assistant_and_prior(
    user_id: str, message_id: int
) -> tuple[str, str] | None:
    """Возвращает (user_msg, assistant_msg) для сообщения с id=message_id."""
    async with session_scope() as session:
        convos = ConversationRepository(session)
        rows = await convos.history(user_id, limit=200)

    target: dict | None = None
    for row in rows:
        if row.get("id") == message_id:
            target = row
            break
    if target is None or target.get("role") != "assistant":
        return None

    # Ищем предыдущий user turn
    assistant_content = target.get("content", "")
    user_content = ""
    target_idx = rows.index(target)
    for i in range(target_idx - 1, -1, -1):
        if rows[i].get("role") == "user":
            user_content = rows[i].get("content", "")
            break
    return user_content, assistant_content


async def record_lesson(
    *, user_id: str, message_id: int | None, score: int, note: str | None = None
) -> bool:
    """Записывает урок в память. Возвращает True, если записали."""
    if score == 0:
        return False  # нейтральная оценка — ничего не учим

    user_msg = ""
    assistant_msg = ""
    if message_id is not None:
        loaded = await _load_assistant_and_prior(user_id, message_id)
        if loaded is not None:
            user_msg, assistant_msg = loaded

    if not assistant_msg and not note:
        # нет ни сообщения, ни комментария — урок пустой
        return False

    lesson = _format_lesson(
        score=score,
        user_msg=user_msg or "(без контекста)",
        assistant_msg=assistant_msg or "(ответа нет)",
        note=note,
    )

    try:
        await default_memory().add(
            [
                MemoryRecord(
                    id="",
                    text=lesson,
                    user_id=user_id,
                    metadata={
                        "kind": "lesson",
                        "score": score,
                        "source": "feedback",
                        "message_id": message_id,
                    },
                )
            ]
        )
        logger.info(
            "📚 lesson recorded: user=%s score=%+d msg_id=%s",
            user_id,
            score,
            message_id,
        )
        return True
    except Exception as exc:  # pragma: no cover
        logger.warning("record_lesson failed: %s", exc)
        return False
