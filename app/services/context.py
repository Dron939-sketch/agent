"""ContextAggregator: единый сборщик контекста для LLM-промпта.

Достаёт из БД профиль, релевантную память, эмоциональный тренд, историю
диалога и форматирует всё в текстовый блок для system message.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db import (
    ConversationRepository,
    EmotionRepository,
    UserRepository,
)
from app.services.emotion import EmotionResult, EmotionService
from app.services.memory import default_memory
from app.services.profile import build_profile_prompt

logger = get_logger(__name__)


@dataclass(slots=True)
class FullContext:
    profile_prompt: str = ""
    recalled: list[str] = field(default_factory=list)
    emotion: EmotionResult | None = None
    emotion_trend: dict[str, Any] = field(default_factory=dict)
    history: list[dict[str, str]] = field(default_factory=list)


class ContextAggregator:
    """Собирает всё необходимое для одного LLM-вызова."""

    def __init__(
        self,
        session: AsyncSession,
        emotion_service: EmotionService | None = None,
    ) -> None:
        self.session = session
        self.emotion_service = emotion_service or EmotionService()

    async def get_full_context(
        self,
        user_id: str,
        current_message: str,
        *,
        history_limit: int = 20,
        recall_limit: int = 3,
    ) -> FullContext:
        ctx = FullContext()

        # 1. История диалога
        convos = ConversationRepository(self.session)
        rows = await convos.history(user_id, limit=history_limit)
        ctx.history = [{"role": r["role"], "content": r["content"]} for r in rows]

        # 2. Профиль (Varitype)
        user = await UserRepository(self.session).get(user_id)
        if user and user.profile:
            try:
                profile_data = json.loads(user.profile)
                ctx.profile_prompt = build_profile_prompt(profile_data)
            except Exception:
                ctx.profile_prompt = ""

        # 3. Эмоция текущего сообщения (быстрая, без сети)
        ctx.emotion = self.emotion_service.detect_from_text(current_message)

        # 4. Эмоциональный тренд (последние 5 событий)
        try:
            ctx.emotion_trend = await EmotionRepository(self.session).trend(user_id, limit=5)
        except Exception as exc:
            logger.warning("emotion trend failed: %s", exc)
            ctx.emotion_trend = {}

        # 5. Релевантная память
        try:
            hits = await default_memory().search(
                current_message, user_id=user_id, top_k=recall_limit
            )
            ctx.recalled = [h.text for h in hits]
        except Exception as exc:
            logger.warning("memory recall failed: %s", exc)
            ctx.recalled = []

        return ctx

    @staticmethod
    def format_for_prompt(ctx: FullContext, base_system: str) -> str:
        """Превращает FullContext в готовый system prompt."""
        parts: list[str] = [base_system]

        if ctx.profile_prompt:
            parts.append(ctx.profile_prompt)

        if ctx.emotion is not None:
            e = ctx.emotion
            parts.append(
                f"СОСТОЯНИЕ ПОЛЬЗОВАТЕЛЯ:\n"
                f"- Эмоция: {e.primary} (intensity {e.intensity}/10)\n"
                f"- Рекомендуемый тон: {e.tone}"
                + ("\n- Нужна поддержка: да" if e.needs_support else "")
            )

        trend = ctx.emotion_trend or {}
        if trend.get("trend") == "volatile":
            parts.append("(эмоциональное состояние нестабильно — будь внимателен и мягок)")
        elif trend.get("trend") == "stable" and trend.get("emotion"):
            parts.append(f"(эмоциональное состояние стабильно: {trend['emotion']})")

        if ctx.recalled:
            memo = "\n".join(f"- {t}" for t in ctx.recalled)
            parts.append(f"РЕЛЕВАНТНАЯ ПАМЯТЬ:\n{memo}")

        return "\n\n".join(parts)
