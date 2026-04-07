"""Daily morning brief: персонализированная сводка для пользователя.

Собирает: эмоциональный тренд + последние факты из памяти + активные
напоминания → прогоняет через LLM для дружелюбного утреннего сообщения.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthenticatedUser
from app.core.logging import get_logger
from app.db import ConversationRepository, EmotionRepository
from app.services.llm import ChatMessage, default_router
from app.services.memory import default_memory

from .deps import get_current_user, get_session

logger = get_logger(__name__)

router = APIRouter(prefix="/api/brief", tags=["brief"])


class BriefResponse(BaseModel):
    text: str
    mood_trend: str
    facts_used: int


@router.get("/morning", response_model=BriefResponse)
async def morning_brief(
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> BriefResponse:
    # Эмоциональный тренд за последние 5 событий
    trend = await EmotionRepository(session).trend(user.user_id, limit=5)

    # Топ факты из памяти, релевантные «утренней рутине»
    facts: list[str] = []
    try:
        hits = await default_memory().search(
            "утро день планы цели важное", user_id=user.user_id, top_k=5
        )
        facts = [h.text for h in hits]
    except Exception as exc:
        logger.warning("brief recall failed: %s", exc)

    # Последние 5 сообщений как контекст
    history = await ConversationRepository(session).history(user.user_id, limit=5)
    history_text = "\n".join(f"[{m['role']}] {m['content']}" for m in history)

    system = (
        "Ты Фреди — утренний друг. Сформируй короткое (4-6 предложений) "
        "дружелюбное утреннее сообщение пользователю на русском. "
        "Учти эмоциональный тренд и важные факты. Без воды, по делу. "
        "Если данных мало — спроси, как настроение или какие планы."
    )

    facts_block = "\n".join(f"- {f}" for f in facts) if facts else "(память пуста)"
    user_prompt = (
        f"Эмоциональный тренд: {trend}\n\n"
        f"Важные факты:\n{facts_block}\n\n"
        f"Последние сообщения:\n{history_text or '(нет истории)'}"
    )

    messages = [
        ChatMessage(role="system", content=system),
        ChatMessage(role="user", content=user_prompt),
    ]

    try:
        resp = await default_router().chat(messages, profile="fast", temperature=0.7, max_tokens=300)  # type: ignore[arg-type]
        text = resp.text.strip()
    except Exception as exc:
        logger.warning("brief LLM failed: %s", exc)
        text = "Доброе утро! Расскажи, как настроение и какие планы на день?"

    return BriefResponse(
        text=text,
        mood_trend=str(trend.get("trend", "no_data")),
        facts_used=len(facts),
    )
