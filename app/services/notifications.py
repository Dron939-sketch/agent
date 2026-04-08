"""Composer для morning brief + рассылка через WebPush.

Sprint 5: вызывается из AutonomyLoop. Берёт всех пользователей,
проверяет какой час сейчас в их таймзоне, и тем у кого 9:00 — шлёт
пуш с коротким утренним сообщением.

Timezone берётся из user.context.timezone_offset (часов от UTC).
Дефолт: UTC+3 (Москва), если не задан.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.logging import get_logger
from app.db import EmotionRepository, PushSubscription, User, session_scope
from app.services.llm import ChatMessage, default_router
from app.services.memory import default_memory
from app.services.push import WebPushService

logger = get_logger(__name__)

DEFAULT_TZ_OFFSET_HOURS = 3  # Москва


def _user_local_hour(tz_offset_hours: int) -> int:
    return (datetime.now(timezone.utc) + timedelta(hours=tz_offset_hours)).hour


def _user_today_str(tz_offset_hours: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=tz_offset_hours)).strftime("%Y-%m-%d")


def _get_tz_offset(user: User) -> int:
    if not user.context:
        return DEFAULT_TZ_OFFSET_HOURS
    try:
        ctx = json.loads(user.context)
        return int(ctx.get("timezone_offset", DEFAULT_TZ_OFFSET_HOURS))
    except Exception:
        return DEFAULT_TZ_OFFSET_HOURS


async def compose_brief(user_id: str) -> str:
    """Генерирует короткий утренний бриф через LLMRouter."""
    facts: list[str] = []
    try:
        hits = await default_memory().search(
            "утро день планы цели важное", user_id=user_id, top_k=5
        )
        facts = [h.text for h in hits]
    except Exception:
        pass

    trend: dict = {}
    try:
        async with session_scope() as session:
            trend = await EmotionRepository(session).trend(user_id, limit=5)
    except Exception:
        pass

    facts_block = "\n".join(f"- {f}" for f in facts) if facts else "(память пуста)"
    user_prompt = (
        f"Эмоциональный тренд: {trend}\n\n"
        f"Важные факты:\n{facts_block}\n\n"
        f"Это утренний пуш в 9:00, сформулируй короткое (1-2 предложения) "
        f"тёплое сообщение без воды. Используй многоточие для естественной паузы."
    )
    system = (
        "Ты Фреди — утренний друг. Сформируй короткое (1-2 предложения) "
        "приветствие пользователю, опираясь на его эмоциональный тренд и факты. "
        "Без воды, без вопросов «как дела?». Покажи, что помнишь его."
    )
    messages = [
        ChatMessage(role="system", content=system),
        ChatMessage(role="user", content=user_prompt),
    ]
    try:
        resp = await default_router().chat(messages, profile="fast", temperature=0.7, max_tokens=120)  # type: ignore[arg-type]
        return resp.text.strip()[:200]
    except Exception as exc:
        logger.warning("brief compose failed: %s", exc)
        return "Доброе утро… как настроение сегодня?"


async def send_morning_briefs_due(last_sent: dict[str, str]) -> int:
    """Шлёт пуш всем пользователям, у которых сейчас 9:00 локального времени.

    `last_sent` — внешний кеш `user_id → "YYYY-MM-DD"` чтобы не слать
    дважды в один день после рестарта.
    Возвращает количество отправленных пушей.
    """
    push_service = WebPushService()
    if not push_service.is_configured():
        return 0

    sent = 0
    async with session_scope() as session:
        result = await session.execute(select(User))
        users = list(result.scalars().all())

    for user in users:
        tz = _get_tz_offset(user)
        hour = _user_local_hour(tz)
        if hour != 9:
            continue
        today = _user_today_str(tz)
        if last_sent.get(user.user_id) == today:
            continue

        # Получаем подписки
        async with session_scope() as session:
            sub_result = await session.execute(
                select(PushSubscription).where(PushSubscription.user_id == user.user_id)
            )
            subs = list(sub_result.scalars().all())
        if not subs:
            continue

        text = await compose_brief(user.user_id)
        payload = {
            "title": "Фреди",
            "body": text,
            "icon": "/icon.svg",
            "url": "/"
        }

        for sub in subs:
            try:
                data = json.loads(sub.payload)
            except Exception:
                continue
            ok = await push_service.send(data, payload)
            if ok:
                sent += 1

        last_sent[user.user_id] = today

    return sent
