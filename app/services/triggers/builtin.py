"""Встроенные триггеры для проактивного поведения Фреди.

Sprint 6:
- GoalDeadlineTrigger: предупреждает о приближающихся дедлайнах целей
- HabitReminderTrigger: напоминает о невыполненных привычках
- InactivityTrigger: инициирует контакт при долгом молчании
- MoodCheckTrigger: предлагает поддержку при негативном тренде
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from app.core.logging import get_logger
from app.db import (
    EmotionRepository,
    GoalRepository,
    HabitRepository,
    session_scope,
    User,
)

from .base import Priority, Trigger, TriggerResult

logger = get_logger(__name__)

DEFAULT_TZ_OFFSET = 3  # Moscow


def _get_user_tz(user: User) -> int:
    if not user.context:
        return DEFAULT_TZ_OFFSET
    try:
        ctx = json.loads(user.context)
        return int(ctx.get("timezone_offset", DEFAULT_TZ_OFFSET))
    except Exception:
        return DEFAULT_TZ_OFFSET


def _user_local_now(tz_offset: int) -> datetime:
    tz = timezone(timedelta(hours=tz_offset))
    return datetime.now(tz)


class GoalDeadlineTrigger(Trigger):
    """Предупреждает о целях с приближающимся дедлайном."""

    name = "goal_deadline"
    description = "Предупреждение о дедлайнах целей"

    async def evaluate(self, user_id: str) -> list[TriggerResult]:
        results: list[TriggerResult] = []
        async with session_scope() as session:
            repo = GoalRepository(session)
            goals = await repo.list_active(user_id)

        now = datetime.utcnow()
        for goal in goals:
            if not goal.target_date:
                continue

            days_left = (goal.target_date - now).days

            if days_left < 0:
                # Просрочена
                results.append(TriggerResult(
                    triggered=True,
                    message=f"Дедлайн по цели «{goal.title}» уже прошёл ({-days_left} дн. назад). Хочешь пересмотреть сроки?",
                    title="Фреди — дедлайн",
                    priority=Priority.HIGH,
                    user_id=user_id,
                    source=self.name,
                    data={"goal_id": goal.id, "days_left": days_left},
                ))
            elif days_left <= 1:
                results.append(TriggerResult(
                    triggered=True,
                    message=f"Завтра дедлайн по цели «{goal.title}» (прогресс: {goal.progress_pct}%). Что-то нужно подготовить?",
                    title="Фреди — завтра дедлайн",
                    priority=Priority.HIGH,
                    user_id=user_id,
                    source=self.name,
                    data={"goal_id": goal.id, "days_left": days_left},
                ))
            elif days_left <= 3:
                results.append(TriggerResult(
                    triggered=True,
                    message=f"До дедлайна по «{goal.title}» осталось {days_left} дн. Прогресс: {goal.progress_pct}%.",
                    title="Фреди — скоро дедлайн",
                    priority=Priority.NORMAL,
                    user_id=user_id,
                    source=self.name,
                    data={"goal_id": goal.id, "days_left": days_left},
                ))

        return results


class HabitReminderTrigger(Trigger):
    """Напоминает о ежедневных привычках которые ещё не отмечены."""

    name = "habit_reminder"
    description = "Напоминание о привычках"

    async def evaluate(self, user_id: str) -> list[TriggerResult]:
        results: list[TriggerResult] = []

        async with session_scope() as session:
            # Получаем timezone пользователя
            from sqlalchemy import select
            user_result = await session.execute(
                select(User).where(User.user_id == user_id)
            )
            user = user_result.scalar_one_or_none()
            tz_offset = _get_user_tz(user) if user else DEFAULT_TZ_OFFSET

        local_now = _user_local_now(tz_offset)

        # Напоминаем только вечером (18:00 - 21:00)
        if not (18 <= local_now.hour <= 21):
            return results

        async with session_scope() as session:
            repo = HabitRepository(session)
            habits = await repo.list(user_id)

        today_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
        undone: list[str] = []

        for habit in habits:
            if habit.cadence != "daily":
                continue
            if habit.last_check_at and habit.last_check_at > today_start.replace(tzinfo=None):
                continue  # Уже отмечена сегодня
            undone.append(habit.title)

        if undone:
            titles = ", ".join(f"«{t}»" for t in undone[:3])
            extra = f" и ещё {len(undone) - 3}" if len(undone) > 3 else ""
            results.append(TriggerResult(
                triggered=True,
                message=f"Сегодня ещё не отмечены привычки: {titles}{extra}. Скажи «сделал ...» чтобы отметить.",
                title="Фреди — привычки",
                priority=Priority.NORMAL,
                user_id=user_id,
                source=self.name,
                data={"undone": undone},
            ))

        return results


class InactivityTrigger(Trigger):
    """Инициирует контакт если пользователь давно не общался."""

    name = "inactivity"
    description = "Проактивный контакт при долгом молчании"

    # Порог неактивности (часы)
    threshold_hours: int = 48

    async def evaluate(self, user_id: str) -> list[TriggerResult]:
        from sqlalchemy import select, func
        from app.db import Conversation

        async with session_scope() as session:
            result = await session.execute(
                select(func.max(Conversation.created_at))
                .where(Conversation.user_id == user_id, Conversation.role == "user")
            )
            last_message = result.scalar_one_or_none()

        if not last_message:
            return []

        hours_since = (datetime.utcnow() - last_message).total_seconds() / 3600

        if hours_since >= self.threshold_hours:
            return [TriggerResult(
                triggered=True,
                message="Давно не общались... Как дела? Может, нужна помощь с чем-то?",
                title="Фреди скучает",
                priority=Priority.LOW,
                user_id=user_id,
                source=self.name,
                data={"hours_since": round(hours_since, 1)},
            )]

        return []


class MoodCheckTrigger(Trigger):
    """Предлагает поддержку при негативном эмоциональном тренде."""

    name = "mood_check"
    description = "Поддержка при плохом настроении"

    # Негативные эмоции по Plutchik
    _NEGATIVE = {"sadness", "anger", "fear", "disgust", "grief", "rage", "terror", "loathing",
                 "грусть", "злость", "страх", "отвращение", "тревога", "усталость"}

    async def evaluate(self, user_id: str) -> list[TriggerResult]:
        async with session_scope() as session:
            repo = EmotionRepository(session)
            events = await repo.recent(user_id, limit=5)

        if len(events) < 3:
            return []

        negative_count = sum(
            1 for e in events
            if e.primary.lower() in self._NEGATIVE or e.needs_support
        )

        if negative_count >= 3:
            return [TriggerResult(
                triggered=True,
                message="Заметил, что последнее время тебе непросто... Хочешь поговорить? Я здесь.",
                title="Фреди заботится",
                priority=Priority.HIGH,
                user_id=user_id,
                source=self.name,
                data={"negative_ratio": negative_count / len(events)},
            )]

        return []


def register_builtin_triggers(engine: "TriggerEngine") -> None:  # noqa: F821
    """Регистрирует все встроенные триггеры."""
    engine.register(GoalDeadlineTrigger())
    engine.register(HabitReminderTrigger())
    engine.register(InactivityTrigger())
    engine.register(MoodCheckTrigger())
