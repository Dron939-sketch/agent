"""Async SQLAlchemy engine, session-фабрика, init_db()."""

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


# ======== Post-create_all schema patches ========
#
# `Base.metadata.create_all` создаёт НОВЫЕ таблицы, но не умеет добавлять
# колонки в существующие. Когда прод-БД уже содержит старую версию таблицы,
# а код ожидает новую колонку, нужен явный ALTER TABLE.
#
# Этот список — "бедняцкая миграция": он применяется на каждом старте
# идемпотентно (проверяем через Inspector), безопасно ломается при ошибках
# и не требует Alembic. Когда появится настоящий Alembic — эту секцию удалим.
#
# Формат: (table_name, column_name, column_type_sql, create_index)
_SCHEMA_PATCHES: list[tuple[str, str, str, bool]] = [
    # ROUND 3: Conversation ← ChatSession
    ("fr_conversations", "chat_session_id", "INTEGER", True),
]


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


def _apply_schema_patches(sync_conn) -> None:  # type: ignore[no-untyped-def]
    """Добавляет недостающие колонки в существующие таблицы.

    Выполняется в sync-контексте — передаётся в ``conn.run_sync``. Каждая
    правка обёрнута в свой try/except, чтобы одна ошибка не блокировала
    остальные патчи.
    """
    inspector = inspect(sync_conn)
    for table_name, column_name, column_sql, create_index in _SCHEMA_PATCHES:
        try:
            if not inspector.has_table(table_name):
                continue  # таблицы нет — create_all разберётся на следующем запуске
            existing = {c["name"] for c in inspector.get_columns(table_name)}
            if column_name in existing:
                continue  # уже есть
            sync_conn.exec_driver_sql(
                f'ALTER TABLE "{table_name}" ADD COLUMN {column_name} {column_sql}'
            )
            logger.info("📐 schema patch: %s.%s added", table_name, column_name)

            if create_index:
                index_name = f"ix_{table_name}_{column_name}"
                try:
                    sync_conn.exec_driver_sql(
                        f'CREATE INDEX IF NOT EXISTS "{index_name}" '
                        f'ON "{table_name}" ({column_name})'
                    )
                except Exception as idx_exc:
                    logger.warning(
                        "schema patch: index %s on %s.%s skipped: %s",
                        index_name, table_name, column_name, idx_exc,
                    )
        except Exception as exc:
            logger.warning(
                "schema patch for %s.%s failed (continuing): %s",
                table_name, column_name, exc,
            )


async def init_db() -> None:
    """Создаёт таблицы, если их нет + применяет мини-миграции."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_apply_schema_patches)


async def dispose_db() -> None:
    """Корректно закрывает движок (вызывается на shutdown)."""
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _sessionmaker = None
