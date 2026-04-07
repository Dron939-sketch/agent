"""Async-репозитории, повторяющие API legacy-класса `Database` из main.py.

Это позволяет постепенно мигрировать вызовы без переписывания всех роутеров.
"""

from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Backup, Conversation, Log, Repository, Session, Task, User


# ============ Users ============

class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, user_id: str, username: str, email: str, password_hash: str) -> bool:
        user = User(user_id=user_id, username=username, email=email, password_hash=password_hash)
        self.session.add(user)
        try:
            await self.session.flush()
            return True
        except IntegrityError:
            await self.session.rollback()
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
        result = await self.session.execute(
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .order_by(Conversation.created_at.desc())
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
