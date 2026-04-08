"""Coach endpoints: цели и привычки.

REST для UI + интеграция с chat intent handler.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthenticatedUser
from app.db import GoalRepository, HabitRepository

from .deps import get_current_user, get_session

router = APIRouter(prefix="/api/coach", tags=["coach"])


# === Goals ===


class GoalCreateIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    target_date: datetime | None = None


class GoalUpdateIn(BaseModel):
    progress_pct: int | None = Field(default=None, ge=0, le=100)
    status: str | None = Field(default=None, pattern="^(active|done|paused|dropped)$")


class GoalOut(BaseModel):
    id: int
    title: str
    description: str | None = None
    status: str
    progress_pct: int
    target_date: datetime | None = None
    created_at: datetime


@router.post("/goals", response_model=GoalOut, status_code=status.HTTP_201_CREATED)
async def create_goal(
    body: GoalCreateIn,
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> GoalOut:
    repo = GoalRepository(session)
    goal_id = await repo.add(
        user.user_id,
        body.title,
        description=body.description,
        target_date=body.target_date,
    )
    goal = await repo.get(goal_id)
    if not goal:
        raise HTTPException(500, "create failed")
    return GoalOut(
        id=goal.id,
        title=goal.title,
        description=goal.description,
        status=goal.status,
        progress_pct=goal.progress_pct,
        target_date=goal.target_date,
        created_at=goal.created_at,
    )


@router.get("/goals", response_model=list[GoalOut])
async def list_goals(
    only_active: bool = False,
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[GoalOut]:
    repo = GoalRepository(session)
    items = await repo.list_active(user.user_id) if only_active else await repo.list_all(user.user_id)
    return [
        GoalOut(
            id=g.id,
            title=g.title,
            description=g.description,
            status=g.status,
            progress_pct=g.progress_pct,
            target_date=g.target_date,
            created_at=g.created_at,
        )
        for g in items
    ]


@router.patch("/goals/{goal_id}", response_model=GoalOut)
async def update_goal(
    goal_id: int,
    body: GoalUpdateIn,
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> GoalOut:
    repo = GoalRepository(session)
    goal = await repo.get(goal_id)
    if not goal or goal.user_id != user.user_id:
        raise HTTPException(404, "goal not found")
    if body.progress_pct is not None:
        await repo.update_progress(goal_id, body.progress_pct)
    if body.status is not None:
        await repo.set_status(goal_id, body.status)
    goal = await repo.get(goal_id)
    return GoalOut(
        id=goal.id,
        title=goal.title,
        description=goal.description,
        status=goal.status,
        progress_pct=goal.progress_pct,
        target_date=goal.target_date,
        created_at=goal.created_at,
    )


# === Habits ===


class HabitCreateIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    cadence: str = Field(default="daily", pattern="^(daily|weekly|custom)$")


class HabitOut(BaseModel):
    id: int
    title: str
    cadence: str
    streak: int
    longest_streak: int
    last_check_at: datetime | None = None
    created_at: datetime


class HabitCheckIn(BaseModel):
    note: str | None = None


class HabitCheckResult(BaseModel):
    habit_id: int
    streak: int
    longest_streak: int
    was_already_done_today: bool


@router.post("/habits", response_model=HabitOut, status_code=status.HTTP_201_CREATED)
async def create_habit(
    body: HabitCreateIn,
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> HabitOut:
    repo = HabitRepository(session)
    habit_id = await repo.add(user.user_id, body.title, cadence=body.cadence)
    habit = await repo.get(habit_id)
    if not habit:
        raise HTTPException(500, "create failed")
    return HabitOut(
        id=habit.id,
        title=habit.title,
        cadence=habit.cadence,
        streak=habit.streak,
        longest_streak=habit.longest_streak,
        last_check_at=habit.last_check_at,
        created_at=habit.created_at,
    )


@router.get("/habits", response_model=list[HabitOut])
async def list_habits(
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[HabitOut]:
    repo = HabitRepository(session)
    # Сначала чистим broken streaks
    await repo.reset_broken_streaks(user.user_id)
    items = await repo.list(user.user_id)
    return [
        HabitOut(
            id=h.id,
            title=h.title,
            cadence=h.cadence,
            streak=h.streak,
            longest_streak=h.longest_streak,
            last_check_at=h.last_check_at,
            created_at=h.created_at,
        )
        for h in items
    ]


@router.post("/habits/{habit_id}/check", response_model=HabitCheckResult)
async def check_habit(
    habit_id: int,
    body: HabitCheckIn,
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> HabitCheckResult:
    repo = HabitRepository(session)
    habit = await repo.get(habit_id)
    if not habit or habit.user_id != user.user_id:
        raise HTTPException(404, "habit not found")
    result = await repo.check_in(habit_id, user.user_id, body.note)
    return HabitCheckResult(habit_id=habit_id, **result)
