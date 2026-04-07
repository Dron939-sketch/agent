"""Тесты Sprint 1: emotions Plutchik, intents, feedback, recency, forget."""

from __future__ import annotations

import asyncio
import os

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret")

from app.db import (  # noqa: E402
    FeedbackRepository,
    UserRepository,
    dispose_db,
    init_db,
    session_scope,
)
from app.services.emotion import EmotionService, NEEDS_SUPPORT, VALID_EMOTIONS  # noqa: E402
from app.services.intents import detect_intent  # noqa: E402
from app.services.memory import (  # noqa: E402
    HashEmbedder,
    MemoryRecord,
    SQLVectorStore,
    reset_default_memory,
)


# ======== Plutchik 24 эмоции ========


def test_plutchik_grief_detected() -> None:
    r = EmotionService().detect_from_text("это горе, я опустошен")
    assert r.primary in {"grief", "sadness"}
    assert r.needs_support is True


def test_plutchik_ecstasy_detected() -> None:
    r = EmotionService().detect_from_text("обожаю это, кайф невероятный")
    assert r.primary in {"ecstasy", "joy", "love"}
    assert r.needs_support is False


def test_plutchik_optimism_detected() -> None:
    r = EmotionService().detect_from_text("у меня всё получится, верю в это")
    assert r.primary == "optimism"


def test_plutchik_remorse_detected() -> None:
    r = EmotionService().detect_from_text("мне так стыдно, я виноват")
    assert r.primary == "remorse"
    assert r.needs_support is True


def test_emotion_count_at_least_24() -> None:
    assert len(VALID_EMOTIONS) >= 24


def test_needs_support_set_nonempty() -> None:
    assert "grief" in NEEDS_SUPPORT
    assert "rage" in NEEDS_SUPPORT
    assert "joy" not in NEEDS_SUPPORT


# ======== Intents ========


def test_intent_forget() -> None:
    i = detect_intent("забудь, что я люблю кофе")
    assert i.type == "forget"
    assert "кофе" in i.payload


def test_intent_remember() -> None:
    i = detect_intent("запомни что я работаю программистом")
    assert i.type == "remember"
    assert "программ" in i.payload


def test_intent_list_memory() -> None:
    i = detect_intent("что ты помнишь обо мне?")
    assert i.type == "list_memory"


def test_intent_none_for_normal_message() -> None:
    i = detect_intent("привет, как дела")
    assert i.type == "none"


# ======== Feedback ========


@pytest.mark.asyncio
async def test_feedback_likes_dislikes() -> None:
    await init_db()
    try:
        async with session_scope() as session:
            await UserRepository(session).create("u1", "alice", "a@x.com", "h")
            fb = FeedbackRepository(session)
            await fb.add(user_id="u1", score=1, message_id=10)
            await fb.add(user_id="u1", score=1, message_id=11)
            await fb.add(user_id="u1", score=-1, message_id=12)
            stats = await fb.stats("u1")
            assert stats == {"likes": 2, "dislikes": 1, "total": 3}
    finally:
        await dispose_db()


# ======== Memory: recency + forget ========


@pytest.mark.asyncio
async def test_memory_recency_weighting_and_forget() -> None:
    await init_db()
    reset_default_memory()
    try:
        store = SQLVectorStore(HashEmbedder(dim=128))
        await store.add(
            [
                MemoryRecord(id="", text="Я люблю кофе со сливками", user_id="u1"),
                MemoryRecord(id="", text="Я работаю на Python", user_id="u1"),
                MemoryRecord(id="", text="Завтра встреча", user_id="u1"),
            ]
        )

        # forget по подстроке
        removed = await store.forget("u1", "кофе")
        assert removed == 1

        hits_after = await store.search("кофе сливки", user_id="u1")
        assert all("кофе" not in h.text.lower() for h in hits_after)

        # search ещё работает
        hits = await store.search("python", user_id="u1", top_k=2)
        assert any("python" in h.text.lower() for h in hits)
    finally:
        await dispose_db()
        reset_default_memory()


@pytest.mark.asyncio
async def test_recency_score_boost() -> None:
    """Свежая запись с тем же текстом получает выше score, чем старая."""
    from datetime import datetime, timedelta

    from app.services.memory.sql import _recency_score

    now_score = _recency_score(datetime.utcnow())
    old_score = _recency_score(datetime.utcnow() - timedelta(days=30))
    assert now_score > old_score
    assert 0.99 <= now_score <= 1.0
    assert old_score < 0.5
