"""Background tasks для автономности.

Sprint 5: расширен периодическими задачами:
- self-ping каждые 10 минут (keepalive)
- memory consolidation раз в 24 часа
- morning brief push в 9:00 локального времени каждого пользователя
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, time, timezone
from typing import Optional

import aiohttp

from .logging import get_logger

logger = get_logger(__name__)


class AutonomyLoop:
    def __init__(
        self,
        *,
        ping_interval_seconds: int = 600,
        consolidate_interval_seconds: int = 86400,
        brief_check_interval_seconds: int = 1800,
    ) -> None:
        self.ping_interval = ping_interval_seconds
        self.consolidate_interval = consolidate_interval_seconds
        self.brief_check_interval = brief_check_interval_seconds
        self._task: Optional[asyncio.Task[None]] = None
        self._stop = asyncio.Event()
        self._last_consolidate: datetime | None = None
        self._last_brief_user_day: dict[str, str] = {}  # user_id → "YYYY-MM-DD"

    @property
    def self_url(self) -> str | None:
        return (
            os.environ.get("SELF_PUBLIC_URL")
            or os.environ.get("RENDER_EXTERNAL_URL")
            or None
        )

    async def _ping_self(self) -> None:
        url = self.self_url
        if not url:
            return
        target = url.rstrip("/") + "/keepalive"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(target, timeout=10) as resp:
                    logger.debug("autonomy ping %s -> %s", target, resp.status)
        except Exception as exc:
            logger.debug("autonomy ping failed: %s", exc)

    async def _maybe_consolidate(self) -> None:
        now = datetime.utcnow()
        if (
            self._last_consolidate is not None
            and (now - self._last_consolidate).total_seconds() < self.consolidate_interval
        ):
            return
        self._last_consolidate = now
        try:
            from app.services.memory.consolidator import consolidate_all_users

            stats = await consolidate_all_users()
            logger.info("🧹 daily consolidate: %s", stats)
        except Exception as exc:
            logger.warning("consolidate failed: %s", exc)

    async def _maybe_morning_brief(self) -> None:
        """Шлём утренний бриф в 9:00 локального времени пользователя.

        Timezone берётся из user.context.timezone_offset (часы относительно UTC).
        Если не задан — UTC. Один раз в день на пользователя.
        """
        try:
            from app.services.notifications import send_morning_briefs_due

            sent = await send_morning_briefs_due(self._last_brief_user_day)
            if sent:
                logger.info("🌅 morning briefs sent: %d", sent)
        except Exception as exc:
            logger.debug("morning brief check failed: %s", exc)

    async def _run(self) -> None:
        logger.info(
            "🔁 AutonomyLoop started (ping=%ds, consolidate=%ds, brief_check=%ds, self_url=%s)",
            self.ping_interval,
            self.consolidate_interval,
            self.brief_check_interval,
            self.self_url or "—",
        )
        last_brief_check = datetime.utcnow() - timedelta(seconds=self.brief_check_interval + 1)

        while not self._stop.is_set():
            try:
                await self._ping_self()
            except Exception as exc:  # pragma: no cover
                logger.warning("autonomy ping failed: %s", exc)

            try:
                await self._maybe_consolidate()
            except Exception as exc:  # pragma: no cover
                logger.warning("autonomy consolidate failed: %s", exc)

            now = datetime.utcnow()
            if (now - last_brief_check).total_seconds() >= self.brief_check_interval:
                last_brief_check = now
                try:
                    await self._maybe_morning_brief()
                except Exception as exc:  # pragma: no cover
                    logger.warning("autonomy brief failed: %s", exc)

            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.ping_interval)
            except asyncio.TimeoutError:
                pass

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="freddy-autonomy")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stop.set()
        try:
            await asyncio.wait_for(self._task, timeout=5)
        except asyncio.TimeoutError:
            self._task.cancel()
        self._task = None
        logger.info("🔁 AutonomyLoop stopped")


# Импорт в конце для timedelta
from datetime import timedelta  # noqa: E402

_loop: AutonomyLoop | None = None


def get_autonomy_loop() -> AutonomyLoop:
    global _loop
    if _loop is None:
        _loop = AutonomyLoop()
    return _loop
