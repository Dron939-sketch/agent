"""Async SQLAlchemy engine, session factory, init_db()."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.core.config import Config
from app.core.logging import get_logger

from .models import Base

logger = get_logger(__name__)

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None

_SCHEMA_PATCHES: list[tuple[str, str, str, bool]] = [
    ("fr_conversations", "chat_session_id", "INTEGER", True),
]


def _is_memory_sqlite(url: str) -> bool:
    return ":memory:" in url


def get_engine() -> AsyncEngine:
    global _engine, _sessionmaker
    if _engine is None:
        Config.ensure_dirs()
        kwargs: dict = {"future": True}
        if _is_memory_sqlite(Config.DATABASE_URL):
            kwargs["poolclass"] = StaticPool
            kwargs["connect_args"] = {"check_same_thread": False}
        else:
            # Production pool settings — prevent connection exhaustion
            kwargs["pool_size"] = 20
            kwargs["max_overflow"] = 30
            kwargs["pool_timeout"] = 60
            kwargs["pool_recycle"] = 1800
            kwargs["pool_pre_ping"] = True
        _engine = create_async_engine(Config.DATABASE_URL, **kwargs)
        _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
        logger.info(
            "DB engine created: pool_size=%s, max_overflow=%s",
            kwargs.get("pool_size", "default"),
            kwargs.get("max_overflow", "default"),
        )
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    if _sessionmaker is None:
        get_engine()
    assert _sessionmaker is not None
    return _sessionmaker


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    sm = get_sessionmaker()
    async with sm() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def _apply_schema_patches(sync_conn) -> None:
    inspector = inspect(sync_conn)
    for table_name, column_name, column_sql, create_index in _SCHEMA_PATCHES:
        try:
            if not inspector.has_table(table_name):
                continue
            existing = {c["name"] for c in inspector.get_columns(table_name)}
            if column_name in existing:
                continue
            sync_conn.exec_driver_sql(
                f'ALTER TABLE "{table_name}" ADD COLUMN {column_name} {column_sql}'
            )
            logger.info("schema patch: %s.%s added", table_name, column_name)
            if create_index:
                index_name = f"ix_{table_name}_{column_name}"
                try:
                    sync_conn.exec_driver_sql(
                        f'CREATE INDEX IF NOT EXISTS "{index_name}" ON "{table_name}" ({column_name})'
                    )
                except Exception as idx_exc:
                    logger.warning("schema patch index %s skipped: %s", index_name, idx_exc)
        except Exception as exc:
            logger.warning("schema patch %s.%s failed: %s", table_name, column_name, exc)


async def init_db() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_apply_schema_patches)


async def dispose_db() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _sessionmaker = None
