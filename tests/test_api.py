"""End-to-end тесты HTTP API через httpx.AsyncClient + ASGITransport."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret")

from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.api import create_app  # noqa: E402
from app.db import dispose_db, init_db  # noqa: E402


@pytest.mark.asyncio
async def test_health_and_auth_flow() -> None:
    await init_db()
    try:
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.get("/health")
            assert r.status_code == 200
            assert r.json() == {"status": "ok"}

            r = await client.get("/version")
            assert r.status_code == 200
            assert "version" in r.json()

            r = await client.post(
                "/api/auth/register",
                json={"username": "carol", "email": "carol@example.com", "password": "password1"},
            )
            assert r.status_code == 201, r.text

            r = await client.post(
                "/api/auth/login",
                json={"username": "carol", "password": "password1"},
            )
            assert r.status_code == 200
            tokens = r.json()
            access = tokens["access_token"]

            r = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {access}"})
            assert r.status_code == 200
            assert r.json()["username"] == "carol"

            r = await client.get("/api/auth/me")
            assert r.status_code == 401
    finally:
        await dispose_db()
