"""Тесты для app.auth: argon2, JWT, end-to-end register/login."""

from __future__ import annotations

import os
import time

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret-key-please-do-not-use-in-prod")

from app.auth import (  # noqa: E402
    AuthService,
    TokenError,
    create_pair,
    hash_password,
    verify_access,
    verify_password,
    verify_refresh,
)
from app.db import dispose_db, init_db, session_scope  # noqa: E402


def test_password_hash_roundtrip() -> None:
    h = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", h) is True
    assert verify_password("wrong", h) is False


def test_token_pair_roundtrip() -> None:
    pair = create_pair("user-42")
    assert verify_access(pair.access) == "user-42"
    assert verify_refresh(pair.refresh) == "user-42"


def test_access_token_rejects_refresh() -> None:
    pair = create_pair("u")
    with pytest.raises(TokenError):
        verify_access(pair.refresh)


def test_tampered_token_rejected() -> None:
    pair = create_pair("u")
    bad = pair.access[:-2] + ("aa" if pair.access[-2:] != "aa" else "bb")
    with pytest.raises(TokenError):
        verify_access(bad)


@pytest.mark.asyncio
async def test_register_login_verify_refresh_flow() -> None:
    await init_db()
    try:
        async with session_scope() as session:
            auth = AuthService(session)
            uid = await auth.register("bob", "bob@example.com", "s3cret!")
            assert uid is not None

            duplicate = await auth.register("bob", "bob2@example.com", "s3cret!")
            assert duplicate is None  # username unique

            pair = await auth.login("bob", "s3cret!")
            assert pair is not None

            who = await auth.verify(pair.access)
            assert who is not None
            assert who.username == "bob"

            refreshed = await auth.refresh(pair.refresh)
            assert refreshed is not None
            assert verify_access(refreshed.access) == uid

            assert await auth.login("bob", "wrong") is None
    finally:
        await dispose_db()


def test_time_monotonic_sanity() -> None:
    # sanity-check для модулей, использующих time.time
    assert time.time() > 0
