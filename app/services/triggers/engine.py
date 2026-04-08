"""TriggerEngine — центральный движок проактивных триггеров.

Периодически (каждые eval_interval секунд) проверяет все зарегистрированные
триггеры, собирает сработавшие, фильтрует по приоритету и cooldown,
отправляет уведомления через push + WebSocket.
"""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from datetime import datetime, timedelta

from app.core.logging import get_logger
from app.db import PushSubscription, session_scope
from app.services.push import WebPushService

from .base import Priority, Trigger, TriggerResult

logger = get_logger(__name__)

# Минимальный интервал между уведомлениями одного типа для одного пользователя
DEFAULT_COOLDOWN_MINUTES = 30


class TriggerEngine:
    """Движок проактивных триггеров."""

    def __init__(
        self,
        *,
        eval_interval: float = 60.0,  # секунды между проверками
        min_priority: Priority = Priority.NORMAL,
        cooldown_minutes: int = DEFAULT_COOLDOWN_MINUTES,
    ) -> None:
        self.eval_interval = eval_interval
        self.min_priority = min_priority
        self.cooldown_minutes = cooldown_minutes

        self._triggers: list[Trigger] = []
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self._push = WebPushService()

        # Cooldown tracking: (user_id, trigger_name) → last_fired_at
        self._cooldowns: dict[tuple[str, str], datetime] = defaultdict(lambda: datetime.min)

        # WebSocket subscribers: user_id → set of asyncio.Queue
        self._ws_subscribers: dict[str, set[asyncio.Queue[TriggerResult]]] = defaultdict(set)

    def register(self, trigger: Trigger) -> None:
        """Регистрирует триггер."""
        self._triggers.append(trigger)
        logger.info("Trigger registered: %s", trigger.name)

    def subscribe_ws(self, user_id: str, queue: asyncio.Queue[TriggerResult]) -> None:
        """Подписывает WebSocket на уведомления для пользователя."""
        self._ws_subscribers[user_id].add(queue)

    def unsubscribe_ws(self, user_id: str, queue: asyncio.Queue[TriggerResult]) -> None:
        """Отписывает WebSocket."""
        self._ws_subscribers[user_id].discard(queue)
        if not self._ws_subscribers[user_id]:
            del self._ws_subscribers[user_id]

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="freddy-triggers")
        logger.info(
            "TriggerEngine started (interval=%ds, triggers=%d)",
            self.eval_interval, len(self._triggers),
        )

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stop.set()
        try:
            await asyncio.wait_for(self._task, timeout=5)
        except asyncio.TimeoutError:
            self._task.cancel()
        self._task = None
        logger.info("TriggerEngine stopped")

    async def _run(self) -> None:
        while not self._stop.is_set():
            try:
                await self._evaluate_all()
            except Exception as exc:
                logger.exception("TriggerEngine tick failed: %s", exc)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.eval_interval)
            except asyncio.TimeoutError:
                pass

    async def _evaluate_all(self) -> None:
        """Проверяет все триггеры для всех пользователей."""
        all_results: list[TriggerResult] = []

        for trigger in self._triggers:
            try:
                results = await trigger.evaluate_all_users()
                all_results.extend(results)
            except Exception as exc:
                logger.warning("Trigger %s failed: %s", trigger.name, exc)

        # Фильтруем по приоритету и cooldown
        now = datetime.utcnow()
        for result in all_results:
            if result.priority < self.min_priority:
                continue
            if not result.triggered or not result.message:
                continue

            key = (result.user_id, result.source)
            last_fired = self._cooldowns[key]
            if (now - last_fired) < timedelta(minutes=self.cooldown_minutes):
                continue

            # Уведомляем
            self._cooldowns[key] = now
            await self._notify(result)

    async def _notify(self, result: TriggerResult) -> None:
        """Отправляет уведомление через push и WebSocket."""
        logger.info(
            "Trigger fired: %s for user=%s priority=%s msg=%s",
            result.source, result.user_id, result.priority.name, result.message[:80],
        )

        # 1. WebSocket (real-time для фронта)
        queues = self._ws_subscribers.get(result.user_id, set())
        for queue in queues:
            try:
                queue.put_nowait(result)
            except asyncio.QueueFull:
                pass

        # 2. Push notification
        if self._push.is_configured():
            await self._send_push(result)

    async def _send_push(self, result: TriggerResult) -> None:
        """Отправляет push-уведомление."""
        from sqlalchemy import select

        async with session_scope() as session:
            sub_result = await session.execute(
                select(PushSubscription).where(PushSubscription.user_id == result.user_id)
            )
            subs = list(sub_result.scalars().all())

        if not subs:
            return

        payload = {
            "title": result.title,
            "body": result.message,
            "icon": "/icon.svg",
            "url": "/",
            "tag": f"trigger-{result.source}",
            "data": {
                "source": result.source,
                "priority": result.priority.name,
            },
        }

        for sub in subs:
            try:
                data = json.loads(sub.payload)
                await self._push.send(data, payload)
            except Exception as exc:
                logger.debug("Push failed for trigger %s: %s", result.source, exc)

    async def force_evaluate(self, user_id: str) -> list[TriggerResult]:
        """Принудительная проверка триггеров для конкретного пользователя."""
        results: list[TriggerResult] = []
        for trigger in self._triggers:
            try:
                results.extend(await trigger.evaluate(user_id))
            except Exception as exc:
                logger.warning("Force eval trigger %s failed: %s", trigger.name, exc)
        return [r for r in results if r.triggered and r.message]


# === Singleton ===

_engine: TriggerEngine | None = None


def get_trigger_engine() -> TriggerEngine:
    global _engine
    if _engine is None:
        _engine = TriggerEngine()
    return _engine
