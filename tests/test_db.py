"""Async smoke-тесты для нового слоя БД."""

from __future__ import annotations

import os

import pytest

# Используем in-memory SQLite, чтобы не трогать реальную data/assistant.db
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

from app.db import (  # noqa: E402
    ConversationRepository,
    UserRepository,
    dispose_db,
    init_db,
    session_scope,
)


@pytest.mark.asyncio
async def test_user_and_conversation_roundtrip() -> None:
    await init_db()
    try:
        async with session_scope() as session:
            users = UserRepository(session)
            convos = ConversationRepository(session)

            ok = await users.create("u1", "alice", "alice@example.com", "hash")
            assert ok is True

            duplicate = await users.create("u2", "alice", "alice2@example.com", "hash")
            assert duplicate is False  # username unique

            user = await users.get_by_username("alice")
            assert user is not None
            assert user.user_id == "u1"

            await convos.add("u1", "user", "привет")
            await convos.add("u1", "assistant", "здравствуй")

        async with session_scope() as session:
            convos = ConversationRepository(session)
            history = await convos.history("u1")
            assert [m["role"] for m in history] == ["user", "assistant"]
            assert history[0]["content"] == "привет"
    finally:
        await dispose_db()
