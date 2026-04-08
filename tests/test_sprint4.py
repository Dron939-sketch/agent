"""Sprint 4 tests: cache, MMR diversity, dashboard, tool-use scaffolding."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret")

from app.db import EmotionRepository, UserRepository, dispose_db, init_db, session_scope  # noqa: E402
from app.services.memory import (  # noqa: E402
    HashEmbedder,
    MemoryRecord,
    SQLVectorStore,
    reset_default_memory,
)
from app.services.memory.cache import CachedEmbedder  # noqa: E402
from app.services.memory.sql import _mmr_select  # noqa: E402


# ======== CachedEmbedder ========


@pytest.mark.asyncio
async def test_cached_embedder_hit_miss() -> None:
    inner = HashEmbedder(dim=64)
    cached = CachedEmbedder(inner, capacity=100)

    # Первый вызов — miss
    v1 = await cached.embed(["hello"])
    assert cached.misses == 1
    assert cached.hits == 0

    # Второй — hit
    v2 = await cached.embed(["hello"])
    assert v1 == v2
    assert cached.hits == 1

    # Новый текст — miss
    await cached.embed(["world"])
    assert cached.misses == 2

    stats = cached.stats()
    assert stats["size"] == 2
    assert stats["hits"] == 1
    assert stats["misses"] == 2


@pytest.mark.asyncio
async def test_cached_embedder_lru_eviction() -> None:
    inner = HashEmbedder(dim=64)
    cached = CachedEmbedder(inner, capacity=3)
    await cached.embed(["a", "b", "c"])
    assert cached.stats()["size"] == 3
    # Добавляем 4-й → "a" должен вытесниться
    await cached.embed(["d"])
    assert cached.stats()["size"] == 3
    # "a" → miss снова
    await cached.embed(["a"])
    assert cached.stats()["size"] == 3


# ======== MMR diversity ========


def test_mmr_select_picks_diverse() -> None:
    """MMR должен предпочесть разнообразные точки даже если score чуть ниже."""
    a = MemoryRecord(id="1", text="кофе чёрный", embedding=[1.0, 0.0, 0.0], score=0.95)
    b = MemoryRecord(id="2", text="кофе чёрный с молоком", embedding=[0.99, 0.1, 0.0], score=0.93)
    c = MemoryRecord(id="3", text="люблю собак", embedding=[0.0, 0.0, 1.0], score=0.80)

    out = _mmr_select([a, b, c], top_k=2, diversity_lambda=0.5)
    out_ids = {x.id for x in out}
    # Должны быть a (топ score) и c (разнообразие), а не a+b (почти дубликаты)
    assert "1" in out_ids
    assert "3" in out_ids


def test_mmr_select_respects_top_k() -> None:
    items = [
        MemoryRecord(id=str(i), text=f"t{i}", embedding=[float(i), 0, 0], score=1 - i * 0.1)
        for i in range(10)
    ]
    out = _mmr_select(items, top_k=3)
    assert len(out) == 3


# ======== SQLVectorStore с MMR ========


@pytest.mark.asyncio
async def test_sqlvector_recall_with_diversity() -> None:
    await init_db()
    reset_default_memory()
    try:
        store = SQLVectorStore(HashEmbedder(dim=128))
        # Несколько похожих + одна разная
        await store.add(
            [
                MemoryRecord(id="", text="Я люблю Python", user_id="u1"),
                MemoryRecord(id="", text="Python это мой основной язык", user_id="u1"),
                MemoryRecord(id="", text="Использую Python для работы", user_id="u1"),
                MemoryRecord(id="", text="Боюсь публичных выступлений", user_id="u1"),
            ]
        )
        hits = await store.search("python язык", user_id="u1", top_k=2, diversity=True)
        assert len(hits) == 2
        # Кеш должен сработать на повторе
        await store.search("python язык", user_id="u1", top_k=2)
        stats = store.cache_stats()
        assert stats.get("hits", 0) >= 1
    finally:
        await dispose_db()
        reset_default_memory()


# ======== Dashboard mood ========


@pytest.mark.asyncio
async def test_dashboard_mood_endpoint() -> None:
    from httpx import ASGITransport, AsyncClient

    from app.api import create_app

    await init_db()
    try:
        # Создаём пользователя и пару emotion events
        async with session_scope() as session:
            await UserRepository(session).create("u-mood", "moody", "m@x.com", "h")
            repo = EmotionRepository(session)
            await repo.add("u-mood", "joy", 7, 0.8)
            await repo.add("u-mood", "sadness", 5, 0.6)
            await repo.add("u-mood", "joy", 8, 0.85)

        # Регистрируемся через API чтобы получить токен (пользователь уже есть, registers fail)
        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
            r = await client.post(
                "/api/auth/register",
                json={"username": "moody2", "password": "password1"},
            )
            assert r.status_code == 201
            r = await client.post(
                "/api/auth/login", json={"username": "moody2", "password": "password1"}
            )
            access = r.json()["access_token"]
            user_id_2 = None
            r = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {access}"})
            user_id_2 = r.json()["user_id"]

            # Добавим emotion для нового user
            async with session_scope() as session:
                repo = EmotionRepository(session)
                await repo.add(user_id_2, "love", 9, 0.95)

            r = await client.get(
                "/api/dashboard/mood?days=7",
                headers={"Authorization": f"Bearer {access}"},
            )
            assert r.status_code == 200
            data = r.json()
            assert data["dominant"] == "love"
            assert data["points"][0]["primary"] == "love"
    finally:
        await dispose_db()


# ======== Conversation export ========


@pytest.mark.asyncio
async def test_conversation_export_markdown() -> None:
    from httpx import ASGITransport, AsyncClient

    from app.api import create_app

    await init_db()
    try:
        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
            await client.post(
                "/api/auth/register",
                json={"username": "exporter", "password": "password1"},
            )
            r = await client.post(
                "/api/auth/login",
                json={"username": "exporter", "password": "password1"},
            )
            access = r.json()["access_token"]
            headers = {"Authorization": f"Bearer {access}"}

            # Несколько сообщений напрямую через chat (без LLM, через intent)
            await client.post(
                "/api/chat/",
                headers=headers,
                json={"message": "запомни что я тестирую"},
            )

            r = await client.get(
                "/api/dashboard/export?format=markdown", headers=headers
            )
            assert r.status_code == 200
            text = r.text
            assert "История диалога" in text
            assert "@exporter" in text
    finally:
        await dispose_db()
