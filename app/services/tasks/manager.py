"""ReminderManager — создание, отправка и управление напоминаниями.

Работает поверх существующего TaskScheduler: создаёт Task с task_type="reminder",
регистрирует handler который шлёт push-уведомление и создаёт следующее
повторение при recurrence != None.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.logging import get_logger
from app.db import PushSubscription, Task, TaskRepository, session_scope
from app.services.push import WebPushService

from .date_parser import ParsedDateTime, parse_russian_datetime

logger = get_logger(__name__)

TASK_TYPE_REMINDER = "reminder"


class ReminderManager:
    """Менеджер напоминаний."""

    def __init__(self) -> None:
        self._push = WebPushService()

    async def create_from_text(
        self,
        user_id: str,
        text: str,
        *,
        tz_offset: int = 3,
    ) -> dict[str, Any]:
        """Парсит текст, извлекает дату/время и создаёт напоминание.

        Возвращает dict с полями: task_id, title, scheduled_at, recurrence, confidence.
        Raises ValueError если дата не распознана.
        """
        parsed = parse_russian_datetime(text, tz_offset=tz_offset)

        if parsed.dt is None and parsed.recurrence is None:
            raise ValueError(f"Не удалось распознать время в: {text!r}")

        title = parsed.remaining_text or text
        return await self.create(
            user_id=user_id,
            title=title,
            scheduled_at=parsed.dt,
            recurrence=parsed.recurrence,
            original_text=text,
        )

    async def create(
        self,
        user_id: str,
        title: str,
        *,
        scheduled_at: datetime | None = None,
        recurrence: str | None = None,
        original_text: str = "",
    ) -> dict[str, Any]:
        """Создаёт напоминание напрямую."""
        if scheduled_at is None:
            # Default: через 1 час
            scheduled_at = datetime.utcnow() + timedelta(hours=1)

        data = {
            "title": title,
            "recurrence": recurrence,
            "original_text": original_text,
        }

        async with session_scope() as session:
            task_id = await TaskRepository(session).add(
                user_id=user_id,
                task_type=TASK_TYPE_REMINDER,
                data=data,
                scheduled_at=scheduled_at,
            )

        logger.info(
            "Reminder created: id=%d user=%s title=%r at=%s rec=%s",
            task_id, user_id, title, scheduled_at, recurrence,
        )

        return {
            "task_id": task_id,
            "title": title,
            "scheduled_at": scheduled_at.isoformat(),
            "recurrence": recurrence,
        }

    async def list_pending(self, user_id: str) -> list[dict[str, Any]]:
        """Список активных напоминаний пользователя."""
        from sqlalchemy import select

        async with session_scope() as session:
            result = await session.execute(
                select(Task).where(
                    Task.user_id == user_id,
                    Task.task_type == TASK_TYPE_REMINDER,
                    Task.status == "pending",
                ).order_by(Task.scheduled_at)
            )
            tasks = list(result.scalars().all())

        return [
            {
                "id": t.id,
                "title": json.loads(t.data).get("title", "") if t.data else "",
                "scheduled_at": t.scheduled_at.isoformat() if t.scheduled_at else None,
                "recurrence": json.loads(t.data).get("recurrence") if t.data else None,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in tasks
        ]

    async def cancel(self, task_id: int, user_id: str) -> bool:
        """Отменяет напоминание."""
        from sqlalchemy import select

        async with session_scope() as session:
            result = await session.execute(
                select(Task).where(
                    Task.id == task_id,
                    Task.user_id == user_id,
                    Task.task_type == TASK_TYPE_REMINDER,
                    Task.status == "pending",
                )
            )
            task = result.scalar_one_or_none()
            if not task:
                return False
            await TaskRepository(session).update_status(task_id, "done", result={"cancelled": True})
        return True

    async def snooze(self, task_id: int, user_id: str, minutes: int = 15) -> dict[str, Any] | None:
        """Откладывает напоминание на N минут."""
        from sqlalchemy import select, update as sa_update

        async with session_scope() as session:
            result = await session.execute(
                select(Task).where(
                    Task.id == task_id,
                    Task.user_id == user_id,
                    Task.task_type == TASK_TYPE_REMINDER,
                )
            )
            task = result.scalar_one_or_none()
            if not task:
                return None

            new_time = datetime.utcnow() + timedelta(minutes=minutes)
            await session.execute(
                sa_update(Task).where(Task.id == task_id).values(
                    scheduled_at=new_time,
                    status="pending",
                    executed_at=None,
                )
            )

        return {
            "task_id": task_id,
            "new_scheduled_at": new_time.isoformat(),
            "snoozed_minutes": minutes,
        }

    # === Handler для TaskScheduler ===

    async def handle_reminder(self, user_id: str | None, data: dict[str, Any]) -> dict[str, Any]:
        """Вызывается TaskScheduler когда наступает время напоминания."""
        if not user_id:
            return {"error": "no user_id"}

        title = data.get("title", "Напоминание")
        recurrence = data.get("recurrence")

        # Отправляем push
        sent = await self._send_push(user_id, title)

        # Создаём следующее напоминание при recurrence
        next_id: int | None = None
        if recurrence:
            next_dt = self._next_occurrence(recurrence)
            if next_dt:
                result = await self.create(
                    user_id=user_id,
                    title=title,
                    scheduled_at=next_dt,
                    recurrence=recurrence,
                    original_text=data.get("original_text", ""),
                )
                next_id = result["task_id"]

        return {
            "push_sent": sent,
            "title": title,
            "next_task_id": next_id,
        }

    async def _send_push(self, user_id: str, title: str) -> int:
        """Отправляет push-уведомление всем подпискам пользователя."""
        if not self._push.is_configured():
            logger.debug("Push not configured, skipping reminder push")
            return 0

        from sqlalchemy import select

        async with session_scope() as session:
            result = await session.execute(
                select(PushSubscription).where(PushSubscription.user_id == user_id)
            )
            subs = list(result.scalars().all())

        if not subs:
            logger.debug("No push subscriptions for user %s", user_id)
            return 0

        payload = {
            "title": "Фреди — напоминание",
            "body": title,
            "icon": "/icon.svg",
            "url": "/",
            "tag": "reminder",
        }

        sent = 0
        for sub in subs:
            try:
                sub_data = json.loads(sub.payload)
                ok = await self._push.send(sub_data, payload)
                if ok:
                    sent += 1
            except Exception as exc:
                logger.warning("Push failed for sub %s: %s", sub.id, exc)

        return sent

    @staticmethod
    def _next_occurrence(recurrence: str) -> datetime | None:
        """Вычисляет следующее время напоминания."""
        now = datetime.utcnow()
        if recurrence == "daily":
            return now + timedelta(days=1)
        if recurrence == "weekly":
            return now + timedelta(weeks=1)
        if recurrence == "monthly":
            return now + timedelta(days=30)
        return None


# === Singleton ===

_manager: ReminderManager | None = None


def get_reminder_manager() -> ReminderManager:
    global _manager
    if _manager is None:
        _manager = ReminderManager()
    return _manager
