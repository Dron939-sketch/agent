"""Тесты для app.services: LLM stub, scheduler end-to-end."""

from __future__ import annotations

import asyncio
import os

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret")

from app.db import dispose_db, init_db  # noqa: E402
from app.services import DeepSeekClient, TaskScheduler  # noqa: E402


@pytest.mark.asyncio
async def test_deepseek_without_key_returns_fallback() -> None:
    client = DeepSeekClient(api_key="")
    out = await client.chat([{"role": "user", "content": "ping"}])
    assert "недоступен" in out.lower() or "ошибка" in out.lower()


@pytest.mark.asyncio
async def test_scheduler_executes_handler() -> None:
    await init_db()
    try:
        scheduler = TaskScheduler(poll_interval=0.1)
        results: list[dict] = []

        async def handler(user_id, data):
            results.append({"user": user_id, "data": data})
            return {"ok": True}

        scheduler.register("test.echo", handler)
        await scheduler.schedule("u1", "test.echo", {"x": 1})
        await scheduler.start()
        await asyncio.sleep(0.4)
        await scheduler.stop()

        assert results == [{"user": "u1", "data": {"x": 1}}]
    finally:
        await dispose_db()
