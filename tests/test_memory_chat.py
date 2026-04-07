"""Тесты SQL-backed memory store + chat integration."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret")

from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.api import create_app  # noqa: E402
from app.db import dispose_db, init_db  # noqa: E402
from app.services.memory import (  # noqa: E402
    HashEmbedder,
    MemoryRecord,
    SQLVectorStore,
    reset_default_memory,
)


@pytest.mark.asyncio
async def test_sql_vector_store_persists_and_searches() -> None:
    await init_db()
    try:
        store = SQLVectorStore(HashEmbedder(dim=128))
        await store.add(
            [
                MemoryRecord(id="", text="Я работаю над AI-помощником на Python", user_id="alice"),
                MemoryRecord(id="", text="Завтра встреча по продукту в 10:00", user_id="alice"),
                MemoryRecord(id="", text="Боб любит котов", user_id="bob"),
            ]
        )
        # пере-создаём store: данные должны жить в БД
        store2 = SQLVectorStore(HashEmbedder(dim=128))
        hits = await store2.search("python", user_id="alice", top_k=2)
        assert len(hits) >= 1
        assert any("Python" in h.text for h in hits)

        # изоляция
        bob = await store2.search("Python", user_id="bob", top_k=5)
        assert all(h.user_id == "bob" for h in bob)

        removed = await store2.delete_user("alice")
        assert removed >= 3
        assert await store2.search("python", user_id="alice") == []
    finally:
        await dispose_db()


@pytest.mark.asyncio
async def test_chat_integration_stores_memory_after_message(monkeypatch) -> None:
    """End-to-end: register → POST /api/chat/ → memory должна вырасти."""
    await init_db()
    reset_default_memory()
    try:
        # подмена LLM-роутера: возвращает фиктивный ответ без сети
        from app.services import llm as llm_pkg
        from app.services.llm import ChatResponse, LLMRouter, Usage

        class _Stub:
            name = "stub"
            model = "stub-1"

            async def chat(self, messages, *, temperature=0.7, max_tokens=2000):
                return ChatResponse(text="OK, понял", model=self.model, usage=Usage())

            async def stream(self, messages, *, temperature=0.7, max_tokens=2000):
                if False:
                    yield ""

        monkeypatch.setattr(
            llm_pkg, "_router", LLMRouter(profiles={"smart": [_Stub()], "fast": [_Stub()]})
        )

        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
            r = await client.post(
                "/api/auth/register",
                json={"username": "mem", "email": "mem@example.com", "password": "password1"},
            )
            assert r.status_code == 201
            r = await client.post(
                "/api/auth/login", json={"username": "mem", "password": "password1"}
            )
            access = r.json()["access_token"]
            headers = {"Authorization": f"Bearer {access}"}

            r = await client.post(
                "/api/chat/",
                headers=headers,
                json={"message": "Я люблю SQLAlchemy", "use_memory": True, "profile": "smart"},
            )
            assert r.status_code == 200, r.text
            assert r.json()["reply"] == "OK, понял"

            # второе сообщение должно увидеть recall
            r2 = await client.post(
                "/api/chat/",
                headers=headers,
                json={"message": "Что я люблю?", "use_memory": True, "profile": "smart"},
            )
            assert r2.status_code == 200
            recalled_texts = " ".join(r2.json()["recalled"]).lower()
            assert "sqlalchemy" in recalled_texts
    finally:
        await dispose_db()
        reset_default_memory()
