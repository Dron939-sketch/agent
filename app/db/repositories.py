"""Async-репозитории для Фреди."""

from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    Backup,
    Conversation,
    EmotionEvent,
    Log,
    Memory,
    Repository,
    Session,
    Task,
    User,
)


# ============ Users ============

class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, user_id: str, username: str, email: str, password_hash: str) -> bool:
        """Создаёт пользователя в **savepoint**, чтобы IntegrityError на
        дубликате не откатывал предыдущие успешные операции в той же сессии.
        """
        try:
            async with self.session.begin_nested():
                self.session.add(
                    User(
                        user_id=user_id,
                        username=username,
                        email=email,
                        password_hash=password_hash,
                    )
                )
            return True
        except IntegrityError:
            return False

    async def get(self, user_id: str) -> Optional[User]:
        return await self.session.get(User, user_id)

    async def get_by_username(self, username: str) -> Optional[User]:
        result = await self.session.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()

    async def update_profile(self, user_id: str, profile: dict[str, Any]) -> None:
        await self.session.execute(
            update(User).where(User.user_id == user_id).values(profile=json.dumps(profile))
        )

    async def update_context(self, user_id: str, context: dict[str, Any]) -> None:
        await self.session.execute(
            update(User).where(User.user_id == user_id).values(context=json.dumps(context))
        )

    async def update_settings(self, user_id: str, settings: dict[str, Any]) -> None:
        await self.session.execute(
            update(User).where(User.user_id == user_id).values(settings=json.dumps(settings))
        )


# ============ Sessions ============

class SessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, user_id: str, expires_days: int = 7) -> str:
        token = secrets.token_hex(32)
        expires_at = datetime.utcnow() + timedelta(days=expires_days)
        self.session.add(Session(token=token, user_id=user_id, expires_at=expires_at))
        await self.session.flush()
        return token

    async def get(self, token: str) -> Optional[Session]:
        result = await self.session.execute(
            select(Session).where(Session.token == token, Session.expires_at > datetime.utcnow())
        )
        return result.scalar_one_or_none()

    async def delete(self, token: str) -> None:
        await self.session.execute(delete(Session).where(Session.token == token))


# ============ Conversations ============

class ConversationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, user_id: str, role: str, content: str, metadata: dict[str, Any] | None = None) -> None:
        self.session.add(
            Conversation(
                user_id=user_id,
                role=role,
                content=content,
                extra_metadata=json.dumps(metadata or {}),
            )
        )
        await self.session.flush()

    async def history(self, user_id: str, limit: int = 50) -> list[dict[str, Any]]:
        # Сортировка по id DESC даёт стабильный порядок даже когда несколько
        # сообщений вставлены с одинаковым created_at (бывает в SQLite).
        result = await self.session.execute(
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .order_by(Conversation.id.desc())
            .limit(limit)
        )
        rows = result.scalars().all()
        return [
            {"role": r.role, "content": r.content, "timestamp": r.created_at}
            for r in reversed(rows)
        ]

    async def clear(self, user_id: str, days: int = 30) -> None:
        cutoff = datetime.utcnow() - timedelta(days=days)
        await self.session.execute(
            delete(Conversation).where(
                Conversation.user_id == user_id, Conversation.created_at < cutoff
            )
        )


# ============ Tasks ============

class TaskRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(
        self,
        user_id: str,
        task_type: str,
        data: dict[str, Any],
        scheduled_at: datetime | None = None,
    ) -> int:
        task = Task(
            user_id=user_id,
            task_type=task_type,
            data=json.dumps(data),
            scheduled_at=scheduled_at,
        )
        self.session.add(task)
        await self.session.flush()
        return task.id

    async def pending(self) -> list[Task]:
        now = datetime.utcnow()
        result = await self.session.execute(
            select(Task).where(
                Task.status == "pending",
                (Task.scheduled_at.is_(None)) | (Task.scheduled_at <= now),
            )
        )
        return list(result.scalars().all())

    async def update_status(
        self,
        task_id: int,
        status: str,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        await self.session.execute(
            update(Task)
            .where(Task.id == task_id)
            .values(
                status=status,
                executed_at=datetime.utcnow(),
                result=json.dumps(result or {}),
                error=error,
            )
        )


# ============ Logs / Backups / Repositories ============

class LogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, level: str, message: str, metadata: dict[str, Any] | None = None) -> None:
        self.session.add(Log(level=level, message=message, extra_metadata=json.dumps(metadata or {})))
        await self.session.flush()


class BackupRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, backup_path: str, size: int) -> None:
        self.session.add(Backup(backup_path=backup_path, size=size))
        await self.session.flush()

    async def list(self) -> list[Backup]:
        result = await self.session.execute(select(Backup).order_by(Backup.created_at.desc()))
        return list(result.scalars().all())


class RepoRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, user_id: str, repo_name: str, repo_url: str) -> None:
        self.session.add(Repository(user_id=user_id, repo_name=repo_name, repo_url=repo_url))
        await self.session.flush()

    async def list(self, user_id: str) -> list[Repository]:
        result = await self.session.execute(
            select(Repository)
            .where(Repository.user_id == user_id)
            .order_by(Repository.created_at.desc())
        )
        return list(result.scalars().all())


# ============ Memories ============

class MemoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(
        self,
        user_id: str,
        text: str,
        embedding: list[float],
        *,
        kind: str = "message",
        metadata: dict[str, Any] | None = None,
    ) -> int:
        memory = Memory(
            user_id=user_id,
            text=text,
            embedding=json.dumps(embedding),
            kind=kind,
            extra_metadata=json.dumps(metadata or {}),
        )
        self.session.add(memory)
        await self.session.flush()
        return memory.id

    async def list_for_user(self, user_id: str, limit: int = 1000) -> list[Memory]:
        result = await self.session.execute(
            select(Memory)
            .where(Memory.user_id == user_id)
            .order_by(Memory.id.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def count_for_user(self, user_id: str) -> int:
        result = await self.session.execute(
            select(func.count()).select_from(Memory).where(Memory.user_id == user_id)
        )
        return int(result.scalar() or 0)

    async def delete_user(self, user_id: str) -> int:
        # rowcount aiosqlite ненадёжен — считаем заранее
        count = await self.count_for_user(user_id)
        await self.session.execute(delete(Memory).where(Memory.user_id == user_id))
        return count


# ============ Emotions (PR 4.5) ============

class EmotionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(
        self,
        user_id: str,
        primary: str,
        intensity: int,
        confidence: float,
        *,
        tone: str | None = None,
        needs_support: bool = False,
        source: str = "text",
    ) -> int:
        event = EmotionEvent(
            user_id=user_id,
            primary=primary,
            intensity=intensity,
            confidence=confidence,
            tone=tone,
            needs_support=1 if needs_support else 0,
            source=source,
        )
        self.session.add(event)
        await self.session.flush()
        return event.id

    async def recent(self, user_id: str, limit: int = 10) -> list[EmotionEvent]:
        result = await self.session.execute(
            select(EmotionEvent)
            .where(EmotionEvent.user_id == user_id)
            .order_by(EmotionEvent.id.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def trend(self, user_id: str, limit: int = 5) -> dict[str, Any]:
        events = await self.recent(user_id, limit=limit)
        if not events:
            return {"trend": "no_data", "stability": 1.0}
        emotions = [e.primary for e in events]
        unique = set(emotions)
        if len(unique) == 1:
            return {"trend": "stable", "stability": 0.9, "emotion": emotions[0]}
        if len(unique) == 2:
            return {"trend": "shifting", "stability": 0.6, "emotions": list(unique)}
        return {"trend": "volatile", "stability": 0.3, "emotions": list(unique)}
