"""Базовые типы для системы триггеров."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime


class Priority(enum.IntEnum):
    """Приоритет триггера. Чем выше — тем важнее."""
    LOW = 1       # Информационные: погода, новости
    NORMAL = 5    # Напоминания, задачи
    HIGH = 8      # Дедлайны, важные события
    CRITICAL = 10 # Срочные: скоро встреча, упал CI


@dataclass(slots=True)
class TriggerResult:
    """Результат срабатывания триггера."""
    triggered: bool
    message: str = ""
    title: str = "Фреди"
    priority: Priority = Priority.NORMAL
    user_id: str = ""
    source: str = ""  # имя триггера
    data: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)


class Trigger:
    """Базовый класс триггера. Наследники реализуют evaluate()."""

    name: str = "base"
    description: str = ""

    async def evaluate(self, user_id: str) -> list[TriggerResult]:
        """Проверяет условия и возвращает список сработавших триггеров.

        Может вернуть пустой список (ничего не произошло) или несколько результатов.
        """
        return []

    async def evaluate_all_users(self) -> list[TriggerResult]:
        """Проверяет для всех пользователей. По умолчанию — итерирует всех."""
        from sqlalchemy import select
        from app.db import User, session_scope

        async with session_scope() as session:
            result = await session.execute(select(User.user_id))
            user_ids = [row[0] for row in result.all()]

        results: list[TriggerResult] = []
        for uid in user_ids:
            try:
                results.extend(await self.evaluate(uid))
            except Exception:
                pass
        return results
