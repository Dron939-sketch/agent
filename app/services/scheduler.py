"""Async-планировщик задач поверх TaskRepository.

Заменяет legacy `TaskScheduler` из main.py: тот же контракт, но без
синхронного sqlite3 в event loop.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from app.core.logging import get_logger
from app.db import TaskRepository, session_scope

logger = get_logger(__name__)

Handler = Callable[[str | None, dict[str, Any]], Awaitable[dict[str, Any]]]


class TaskScheduler:
    """Простейший пуллер очереди `tasks` с интервалом `poll_interval` сек."""

    def __init__(self, poll_interval: float = 5.0) -> None:
        self.poll_interval = poll_interval
        self._handlers: dict[str, Handler] = {}
        self._task: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()

    def register(self, task_type: str, handler: Handler) -> None:
        self._handlers[task_type] = handler

    async def schedule(
        self,
        user_id: str | None,
        task_type: str,
        data: dict[str, Any],
        scheduled_at: datetime | None = None,
    ) -> int:
        async with session_scope() as session:
            return await TaskRepository(session).add(user_id or "", task_type, data, scheduled_at)

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stopping.clear()
        self._task = asyncio.create_task(self._run(), name="freddy-scheduler")
        logger.info("Scheduler started")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stopping.set()
        try:
            await asyncio.wait_for(self._task, timeout=self.poll_interval + 1)
        except asyncio.TimeoutError:
            self._task.cancel()
        self._task = None
        logger.info("Scheduler stopped")

    async def _run(self) -> None:
        while not self._stopping.is_set():
            try:
                await self._tick()
            except Exception as exc:  # pragma: no cover
                logger.exception("Scheduler tick failed: %s", exc)
            try:
                await asyncio.wait_for(self._stopping.wait(), timeout=self.poll_interval)
            except asyncio.TimeoutError:
                pass

    async def _tick(self) -> None:
        async with session_scope() as session:
            repo = TaskRepository(session)
            pending = await repo.pending()
        for task in pending:
            handler = self._handlers.get(task.task_type)
            if handler is None:
                logger.warning("No handler for task_type=%s", task.task_type)
                async with session_scope() as session:
                    await TaskRepository(session).update_status(
                        task.id, "failed", error="no handler"
                    )
                continue
            try:
                import json

                data = json.loads(task.data) if task.data else {}
                result = await handler(task.user_id, data)
                async with session_scope() as session:
                    await TaskRepository(session).update_status(task.id, "done", result=result)
            except Exception as exc:
                logger.exception("Task %s failed: %s", task.id, exc)
                async with session_scope() as session:
                    await TaskRepository(session).update_status(
                        task.id, "failed", error=str(exc)
                    )
