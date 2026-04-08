"""Sprint 6 tests: TriggerEngine, builtin triggers, priority, cooldown."""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret")

from app.services.triggers.base import Priority, Trigger, TriggerResult  # noqa: E402
from app.services.triggers.engine import TriggerEngine  # noqa: E402


# ======== TriggerResult basics ========


def test_trigger_result_defaults() -> None:
    r = TriggerResult(triggered=True, message="hello", user_id="u1", source="test")
    assert r.priority == Priority.NORMAL
    assert r.title == "Фреди"
    assert r.triggered is True


def test_priority_ordering() -> None:
    assert Priority.LOW < Priority.NORMAL < Priority.HIGH < Priority.CRITICAL
    assert Priority.CRITICAL == 10
    assert Priority.LOW == 1


# ======== Custom trigger ========


class FakeTrigger(Trigger):
    name = "fake"
    description = "Test trigger"

    def __init__(self, results: list[TriggerResult] | None = None):
        self._results = results or []

    async def evaluate(self, user_id: str) -> list[TriggerResult]:
        return [
            TriggerResult(
                triggered=r.triggered,
                message=r.message,
                priority=r.priority,
                user_id=user_id,
                source=self.name,
            )
            for r in self._results
        ]

    async def evaluate_all_users(self) -> list[TriggerResult]:
        return await self.evaluate("test_user")


# ======== TriggerEngine ========


def test_engine_register() -> None:
    engine = TriggerEngine()
    t = FakeTrigger()
    engine.register(t)
    assert len(engine._triggers) == 1
    assert engine._triggers[0].name == "fake"


@pytest.mark.asyncio
async def test_engine_force_evaluate_empty() -> None:
    engine = TriggerEngine()
    results = await engine.force_evaluate("user1")
    assert results == []


@pytest.mark.asyncio
async def test_engine_force_evaluate_with_trigger() -> None:
    engine = TriggerEngine()
    trigger = FakeTrigger([
        TriggerResult(triggered=True, message="test alert", priority=Priority.HIGH, user_id="", source="fake"),
    ])
    engine.register(trigger)
    results = await engine.force_evaluate("user1")
    assert len(results) == 1
    assert results[0].message == "test alert"


@pytest.mark.asyncio
async def test_engine_force_evaluate_filters_not_triggered() -> None:
    engine = TriggerEngine()
    trigger = FakeTrigger([
        TriggerResult(triggered=False, message="should not show", priority=Priority.HIGH, user_id="", source="fake"),
        TriggerResult(triggered=True, message="visible", priority=Priority.NORMAL, user_id="", source="fake"),
    ])
    engine.register(trigger)
    results = await engine.force_evaluate("user1")
    assert len(results) == 1
    assert results[0].message == "visible"


@pytest.mark.asyncio
async def test_engine_force_evaluate_filters_empty_message() -> None:
    engine = TriggerEngine()
    trigger = FakeTrigger([
        TriggerResult(triggered=True, message="", priority=Priority.HIGH, user_id="", source="fake"),
    ])
    engine.register(trigger)
    results = await engine.force_evaluate("user1")
    assert len(results) == 0


# ======== WebSocket subscription ========


def test_ws_subscribe_unsubscribe() -> None:
    engine = TriggerEngine()
    q: asyncio.Queue[TriggerResult] = asyncio.Queue()
    engine.subscribe_ws("u1", q)
    assert "u1" in engine._ws_subscribers
    assert q in engine._ws_subscribers["u1"]

    engine.unsubscribe_ws("u1", q)
    assert "u1" not in engine._ws_subscribers


# ======== Cooldown logic ========


@pytest.mark.asyncio
async def test_engine_cooldown_prevents_duplicate() -> None:
    engine = TriggerEngine(cooldown_minutes=60, min_priority=Priority.LOW)
    trigger = FakeTrigger([
        TriggerResult(triggered=True, message="alert", priority=Priority.NORMAL, user_id="", source="fake"),
    ])
    engine.register(trigger)

    # First evaluation should pass
    engine._cooldowns.clear()
    await engine._evaluate_all()

    # Cooldown should be set
    key = ("test_user", "fake")
    assert key in engine._cooldowns

    # Second evaluation within cooldown should NOT notify again
    notify_count = 0
    original_notify = engine._notify

    async def counting_notify(result: TriggerResult) -> None:
        nonlocal notify_count
        notify_count += 1

    engine._notify = counting_notify  # type: ignore
    await engine._evaluate_all()
    assert notify_count == 0  # Blocked by cooldown
