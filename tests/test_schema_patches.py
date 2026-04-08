"""Test the poor-man's schema migration helper in app.db.session.

Проверяет, что `_apply_schema_patches` умеет добавлять недостающую
колонку ``fr_conversations.chat_session_id`` к старой схеме без неё.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret")

from sqlalchemy import inspect  # noqa: E402

from app.db.session import _apply_schema_patches, dispose_db, get_engine, init_db  # noqa: E402


def _has_column(sync_conn, table: str, column: str) -> bool:
    return any(c["name"] == column for c in inspect(sync_conn).get_columns(table))


@pytest.fixture(autouse=True)
async def _fresh_engine():
    # Сбрасываем глобальный singleton между тестами
    import app.db.session as s

    s._engine = None
    s._sessionmaker = None
    yield
    await dispose_db()


async def test_patches_are_idempotent_on_new_db() -> None:
    """Запуск на пустой БД: create_all всё создаёт, patcher не должен
    ничего менять (колонка уже в свежесозданной таблице)."""
    await init_db()
    engine = get_engine()
    async with engine.begin() as conn:
        has_col = await conn.run_sync(
            lambda c: _has_column(c, "fr_conversations", "chat_session_id")
        )
    assert has_col


async def test_patcher_adds_missing_column() -> None:
    """Симулируем старую БД: создаём таблицу БЕЗ chat_session_id, потом
    прогоняем patcher и проверяем, что колонка появилась."""
    engine = get_engine()
    async with engine.begin() as conn:
        # Создаём таблицу «старой схемы» вручную — без chat_session_id
        await conn.exec_driver_sql("DROP TABLE IF EXISTS fr_conversations")
        await conn.exec_driver_sql(
            """
            CREATE TABLE fr_conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id VARCHAR NOT NULL,
                role VARCHAR NOT NULL,
                content TEXT NOT NULL,
                metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        # до патча — колонки нет
        before = await conn.run_sync(
            lambda c: _has_column(c, "fr_conversations", "chat_session_id")
        )
        assert not before

        # применяем patcher
        await conn.run_sync(_apply_schema_patches)

        # после патча — колонка есть
        after = await conn.run_sync(
            lambda c: _has_column(c, "fr_conversations", "chat_session_id")
        )
        assert after


async def test_patcher_is_idempotent_on_second_run() -> None:
    """Второй запуск patcher-а не должен падать и не должен дублировать."""
    await init_db()
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(_apply_schema_patches)
        await conn.run_sync(_apply_schema_patches)
        # колонка всё ещё на месте, без ошибок
        has_col = await conn.run_sync(
            lambda c: _has_column(c, "fr_conversations", "chat_session_id")
        )
    assert has_col


async def test_patcher_skips_missing_table() -> None:
    """Если таблицы нет — patcher не падает, просто пропускает."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.exec_driver_sql("DROP TABLE IF EXISTS fr_conversations")
        # patcher должен тихо проигнорировать отсутствие таблицы
        await conn.run_sync(_apply_schema_patches)
