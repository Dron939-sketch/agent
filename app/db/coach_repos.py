"""Goals & Habits репозитории + сервисная логика streak'ов.

ROUND 1: Фреди превращается в life-coach.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Goal, Habit, HabitCheck


# ============ Goals ============


class GoalRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(
        self,
        user_id: str,
        title: str,
        *,
        description: str | None = None,
        target_date: datetime | None = None,
    ) -> int:
        goal = Goal(
            user_id=user_id,
            title=title.strip(),
            description=description,
            target_date=target_date,
            status="active",
            progress_pct=0,
        )
        self.session.add(goal)
        await self.session.flush()
        return goal.id

    async def list_active(self, user_id: str) -> list[Goal]:
        result = await self.session.execute(
            select(Goal)
            .where(Goal.user_id == user_id, Goal.status == "active")
            .order_by(Goal.id.desc())
        )
        return list(result.scalars().all())

    async def list_all(self, user_id: str, limit: int = 100) -> list[Goal]:
        result = await self.session.execute(
            select(Goal)
            .where(Goal.user_id == user_id)
            .order_by(Goal.id.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def update_progress(self, goal_id: int, progress_pct: int) -> None:
        progress_pct = max(0, min(100, progress_pct))
        new_status = "done" if progress_pct >= 100 else "active"
        await self.session.execute(
            update(Goal)
            .where(Goal.id == goal_id)
            .values(progress_pct=progress_pct, status=new_status)
        )

    async def set_status(self, goal_id: int, status: str) -> None:
        await self.session.execute(
            update(Goal).where(Goal.id == goal_id).values(status=status)
        )

    async def get(self, goal_id: int) -> Goal | None:
        return await self.session.get(Goal, goal_id)


# ============ Habits ============


class HabitRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(
        self,
        user_id: str,
        title: str,
        *,
        cadence: str = "daily",
    ) -> int:
        habit = Habit(
            user_id=user_id,
            title=title.strip(),
            cadence=cadence,
            streak=0,
            longest_streak=0,
        )
        self.session.add(habit)
        await self.session.flush()
        return habit.id

    async def list(self, user_id: str) -> list[Habit]:
        result = await self.session.execute(
            select(Habit).where(Habit.user_id == user_id).order_by(Habit.id.desc())
        )
        return list(result.scalars().all())

    async def get(self, habit_id: int) -> Habit | None:
        return await self.session.get(Habit, habit_id)

    async def find_by_title(self, user_id: str, query: str) -> Habit | None:
        """Поиск привычки по подстроке (case-insensitive, работает с кириллицей).

        SQLite's built-in ``lower()`` is ASCII-only, so мы фильтруем в Python
        через ``casefold`` — Unicode-safe и корректно обрабатывает кириллицу.
        Это оправдано: у одного пользователя редко больше десятков привычек.
        """
        q = query.casefold().strip()
        if not q:
            return None
        result = await self.session.execute(
            select(Habit).where(Habit.user_id == user_id).order_by(Habit.id.desc())
        )
        for habit in result.scalars().all():
            if q in habit.title.casefold():
                return habit
        return None

    async def check_in(self, habit_id: int, user_id: str, note: str | None = None) -> dict:
        """Отмечает выполнение привычки. Обновляет streak."""
        habit = await self.get(habit_id)
        if habit is None:
            return {"streak": 0, "longest_streak": 0, "was_already_done_today": False}

        now = datetime.utcnow()
        was_today = False
        if habit.last_check_at:
            delta = now - habit.last_check_at
            if delta < timedelta(hours=20):
                was_today = True

        if not was_today:
            new_streak = 1
            if habit.last_check_at:
                delta = now - habit.last_check_at
                if delta < timedelta(hours=48):
                    new_streak = habit.streak + 1
            longest = max(habit.longest_streak, new_streak)

            await self.session.execute(
                update(Habit)
                .where(Habit.id == habit_id)
                .values(streak=new_streak, longest_streak=longest, last_check_at=now)
            )

            self.session.add(
                HabitCheck(habit_id=habit_id, user_id=user_id, note=note)
            )
            await self.session.flush()
            return {
                "streak": new_streak,
                "longest_streak": longest,
                "was_already_done_today": False,
            }

        return {
            "streak": habit.streak,
            "longest_streak": habit.longest_streak,
            "was_already_done_today": True,
        }

    async def reset_broken_streaks(self, user_id: str) -> int:
        """Сбрасывает streak'и привычек, которые не отмечались > 36 часов."""
        cutoff = datetime.utcnow() - timedelta(hours=36)
        habits = await self.list(user_id)
        reset_count = 0
        for h in habits:
            if h.last_check_at and h.last_check_at < cutoff and h.streak > 0:
                await self.session.execute(
                    update(Habit).where(Habit.id == h.id).values(streak=0)
                )
                reset_count += 1
        return reset_count

    async def history(self, habit_id: int, limit: int = 30) -> list[HabitCheck]:
        result = await self.session.execute(
            select(HabitCheck)
            .where(HabitCheck.habit_id == habit_id)
            .order_by(HabitCheck.id.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
