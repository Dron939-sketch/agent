"""Async SQLAlchemy engine, session-фабрика, init_db()."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.core.config import Config

from .models import Base

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def _is_memory_sqlite(url: str) -> bool:
    return ":memory:" in url


def get_engine() -> AsyncEngine:
    """Ленивый singleton движка."""
    global _engine, _sessionmaker
    if _engine is None:
        Config.ensure_dirs()
        kwargs: dict = {"future": True}
        # Для in-memory SQLite КРИТИЧНО использовать StaticPool, иначе каждое
        # новое соединение получает свою БД и таблицы init_db() пропадают.
        if _is_memory_sqlite(Config.DATABASE_URL):
            kwargs["poolclass"] = StaticPool
            kwargs["connect_args"] = {"check_same_thread": False}
        _engine = create_async_engine(Config.DATABASE_URL, **kwargs)
        _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    if _sessionmaker is None:
        get_engine()
    assert _sessionmaker is not None
    return _sessionmaker


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Контекст-менеджер с авто-commit/rollback."""
    sm = get_sessionmaker()
    async with sm() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """Создаёт таблицы, если их нет (для dev/тестов; в проде — Alembic)."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def dispose_db() -> None:
    """Корректно закрывает движок (вызывается на shutdown)."""
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _sessionmaker = None
