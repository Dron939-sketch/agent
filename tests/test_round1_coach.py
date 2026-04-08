"""ROUND 1 tests: Goals + Habits + coach intents."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret")

from app.db import (  # noqa: E402
    GoalRepository,
    HabitRepository,
    UserRepository,
    dispose_db,
    init_db,
    session_scope,
)
from app.services.intents import detect_intent  # noqa: E402


# ======== Coach intents ========


def test_intent_goal_set() -> None:
    i = detect_intent("моя цель — выучить английский за полгода")
    assert i.type == "goal_set"
    assert "английский" in i.payload


def test_intent_goal_set_alt() -> None:
    i = detect_intent("хочу достичь финансовой независимости")
    assert i.type == "goal_set"


def test_intent_goal_list() -> None:
    i = detect_intent("покажи мои цели")
    assert i.type == "goal_list"


def test_intent_habit_create() -> None:
    i = detect_intent("новая привычка — медитация по утрам")
    assert i.type == "habit_create"
    assert "медитация" in i.payload.lower()


def test_intent_habit_create_alt() -> None:
    i = detect_intent("буду каждый день читать 10 страниц")
    assert i.type == "habit_create"
    assert "читать" in i.payload.lower()


def test_intent_habit_check() -> None:
    i = detect_intent("сделал утреннюю зарядку")
    assert i.type == "habit_check"
    assert "зарядк" in i.payload.lower()


def test_intent_habit_list() -> None:
    i = detect_intent("какие у меня привычки?")
    assert i.type == "habit_list"


# ======== Goal CRUD ========


@pytest.mark.asyncio
async def test_goal_crud() -> None:
    await init_db()
    try:
        async with session_scope() as session:
            await UserRepository(session).create("u1", "alice", "a@x.com", "h")
            repo = GoalRepository(session)
            gid = await repo.add("u1", "Выучить английский", description="до уровня B2")
            assert gid > 0

            active = await repo.list_active("u1")
            assert len(active) == 1
            assert active[0].title == "Выучить английский"
            assert active[0].progress_pct == 0

            await repo.update_progress(gid, 50)
            goal = await repo.get(gid)
            assert goal.progress_pct == 50
            assert goal.status == "active"

            await repo.update_progress(gid, 100)
            goal = await repo.get(gid)
            assert goal.status == "done"

            active_after = await repo.list_active("u1")
            assert len(active_after) == 0  # done не active
    finally:
        await dispose_db()


# ======== Habit CRUD + Streak ========


@pytest.mark.asyncio
async def test_habit_streak_logic() -> None:
    await init_db()
    try:
        async with session_scope() as session:
            await UserRepository(session).create("u1", "alice", "a@x.com", "h")
            repo = HabitRepository(session)
            hid = await repo.add("u1", "Медитация")

            # Первый check-in: streak = 1
            r1 = await repo.check_in(hid, "u1")
            assert r1["streak"] == 1
            assert r1["longest_streak"] == 1
            assert r1["was_already_done_today"] is False

            # Сразу повторный check-in (тот же день) — не должен увеличить streak
            r2 = await repo.check_in(hid, "u1")
            assert r2["was_already_done_today"] is True
            assert r2["streak"] == 1

            # Проверка списка
            habits = await repo.list("u1")
            assert len(habits) == 1
            assert habits[0].streak == 1
    finally:
        await dispose_db()


@pytest.mark.asyncio
async def test_habit_find_by_title_fuzzy() -> None:
    await init_db()
    try:
        async with session_scope() as session:
            await UserRepository(session).create("u1", "alice", "a@x.com", "h")
            repo = HabitRepository(session)
            await repo.add("u1", "Утренняя зарядка")
            await repo.add("u1", "Чтение перед сном")

            # Поиск по подстроке
            h1 = await repo.find_by_title("u1", "зарядк")
            assert h1 is not None
            assert "Утренняя" in h1.title

            h2 = await repo.find_by_title("u1", "чтение")
            assert h2 is not None
    finally:
        await dispose_db()


# ======== Coach API e2e ========


@pytest.mark.asyncio
async def test_coach_api_goals_e2e() -> None:
    from httpx import ASGITransport, AsyncClient

    from app.api import create_app

    await init_db()
    try:
        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
            await client.post(
                "/api/auth/register",
                json={"username": "coachy", "password": "password1"},
            )
            r = await client.post(
                "/api/auth/login",
                json={"username": "coachy", "password": "password1"},
            )
            access = r.json()["access_token"]
            headers = {"Authorization": f"Bearer {access}"}

            # Создаём цель через chat intent
            r = await client.post(
                "/api/chat/",
                headers=headers,
                json={"message": "моя цель — пробежать марафон"},
            )
            assert r.status_code == 200
            assert "марафон" in r.json()["reply"].lower()

            # Список через coach API
            r = await client.get("/api/coach/goals", headers=headers)
            assert r.status_code == 200
            goals = r.json()
            assert len(goals) >= 1
            assert any("марафон" in g["title"].lower() for g in goals)

            # Обновляем прогресс
            goal_id = goals[0]["id"]
            r = await client.patch(
                f"/api/coach/goals/{goal_id}",
                headers=headers,
                json={"progress_pct": 30},
            )
            assert r.status_code == 200
            assert r.json()["progress_pct"] == 30
    finally:
        await dispose_db()
