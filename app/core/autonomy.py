"""Background tasks для автономности.

`AutonomyLoop` — лёгкий внутренний цикл, который:
- пингует self-URL (`SELF_PUBLIC_URL` или `RENDER_EXTERNAL_URL`) каждые
  10 минут, не давая Render free засыпать;
- запускает консолидацию памяти и периодические триггеры
  (зарезервировано для будущих фич).

Запускается в lifespan FastAPI и отменяется при shutdown.
"""

from __future__ import annotations

import asyncio
import os
from typing import Optional

import aiohttp

from .logging import get_logger

logger = get_logger(__name__)


class AutonomyLoop:
    def __init__(self, *, interval_seconds: int = 600) -> None:
        self.interval = interval_seconds
        self._task: Optional[asyncio.Task[None]] = None
        self._stop = asyncio.Event()

    @property
    def self_url(self) -> str | None:
        # Render автоматически проставляет RENDER_EXTERNAL_URL
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

    async def _run(self) -> None:
        logger.info(
            "🔁 AutonomyLoop started (interval=%ds, self_url=%s)",
            self.interval,
            self.self_url or "—",
        )
        while not self._stop.is_set():
            try:
                await self._ping_self()
            except Exception as exc:  # pragma: no cover
                logger.warning("autonomy iteration failed: %s", exc)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.interval)
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


_loop: AutonomyLoop | None = None


def get_autonomy_loop() -> AutonomyLoop:
    global _loop
    if _loop is None:
        _loop = AutonomyLoop()
    return _loop
