"""Фоновые мониторы: новости, погода, статусы.

Sprint 12: Фреди в фоне следит за важными вещами и уведомляет
когда происходит что-то релевантное для пользователя.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import aiohttp

from app.core.config import Config
from app.core.logging import get_logger
from app.db import KnowledgeRepository, session_scope

from .base import Priority, Trigger, TriggerResult

logger = get_logger(__name__)


class WeatherAlertTrigger(Trigger):
    """Предупреждает о резком изменении погоды."""

    name = "weather_alert"
    description = "Предупреждение о плохой погоде"

    _ALERT_CONDITIONS = {"гроза", "сильный дождь", "снег", "метель", "шторм", "ураган", "ливень", "мороз"}
    _last_check: dict[str, datetime] = {}

    async def evaluate(self, user_id: str) -> list[TriggerResult]:
        # Проверяем не чаще раза в 2 часа
        now = datetime.utcnow()
        if user_id in self._last_check and (now - self._last_check[user_id]).seconds < 7200:
            return []
        self._last_check[user_id] = now

        key = getattr(Config, "OPENWEATHER_API_KEY", None)
        if not key:
            return []

        # Город из контекста пользователя или Moscow по умолчанию
        city = "Moscow"
        try:
            from sqlalchemy import select as sa_select
            async with session_scope() as session:
                from app.db import User
                result = await session.execute(sa_select(User).where(User.user_id == user_id))
                user = result.scalar_one_or_none()
                if user and user.context:
                    import json as _json
                    ctx = _json.loads(user.context)
                    city = ctx.get("city", city)
        except Exception:
            pass

        try:
            url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={key}&units=metric&lang=ru"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=5) as resp:
                    if resp.status != 200:
                        return []
                    data = await resp.json()

            desc = data.get("weather", [{}])[0].get("description", "").lower()
            temp = data.get("main", {}).get("temp", 20)

            alerts: list[str] = []
            for cond in self._ALERT_CONDITIONS:
                if cond in desc:
                    alerts.append(desc)
                    break

            if temp < -15:
                alerts.append(f"сильный мороз ({temp}°C)")
            elif temp > 35:
                alerts.append(f"аномальная жара ({temp}°C)")

            if not alerts:
                return []

            return [TriggerResult(
                triggered=True,
                message=f"Погодный алерт: {', '.join(alerts)}. Одевайся теплее!" if temp < 0 else f"Погодный алерт: {', '.join(alerts)}.",
                title="Фреди — погода",
                priority=Priority.NORMAL,
                user_id=user_id,
                source=self.name,
                data={"temp": temp, "description": desc},
            )]
        except Exception as exc:
            logger.debug("weather alert check failed: %s", exc)
            return []


class InterestNewsTrigger(Trigger):
    """Мониторит новости по интересам пользователя (из Knowledge Graph)."""

    name = "interest_news"
    description = "Новости по интересам пользователя"

    _last_check: dict[str, datetime] = {}

    async def evaluate(self, user_id: str) -> list[TriggerResult]:
        # Проверяем не чаще раза в 4 часа
        now = datetime.utcnow()
        if user_id in self._last_check and (now - self._last_check[user_id]).seconds < 14400:
            return []
        self._last_check[user_id] = now

        # Получаем интересы пользователя из Knowledge Graph
        try:
            async with session_scope() as session:
                repo = KnowledgeRepository(session)
                interest_facts = await repo.get_facts(
                    user_id, category="preference", limit=5
                )
            if not interest_facts:
                return []

            topics = [f.object for f in interest_facts]
            # Пока логируем — для полной реализации нужен News API
            logger.debug("Would check news for user=%s topics=%s", user_id, topics)
            return []  # TODO: интегрировать News API / Tavily

        except Exception:
            return []


class GoalProgressTrigger(Trigger):
    """Периодически предлагает обновить прогресс по целям."""

    name = "goal_progress"
    description = "Напоминание обновить прогресс целей"

    async def evaluate(self, user_id: str) -> list[TriggerResult]:
        from app.db import GoalRepository

        results: list[TriggerResult] = []

        async with session_scope() as session:
            repo = GoalRepository(session)
            goals = await repo.list_active(user_id)

        for goal in goals:
            if not goal.updated_at:
                continue
            days_since_update = (datetime.utcnow() - goal.updated_at).days

            if days_since_update >= 7 and goal.progress_pct < 100:
                results.append(TriggerResult(
                    triggered=True,
                    message=f"Давно не обновлял прогресс по «{goal.title}» (сейчас {goal.progress_pct}%). Как успехи?",
                    title="Фреди — прогресс",
                    priority=Priority.LOW,
                    user_id=user_id,
                    source=self.name,
                    data={"goal_id": goal.id, "days_since": days_since_update},
                ))

        return results


def register_monitor_triggers(engine: "TriggerEngine") -> None:  # noqa: F821
    """Регистрирует мониторинговые триггеры."""
    engine.register(WeatherAlertTrigger())
    engine.register(InterestNewsTrigger())
    engine.register(GoalProgressTrigger())
