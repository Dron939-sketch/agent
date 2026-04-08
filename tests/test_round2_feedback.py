"""ROUND 2 tests: feedback → lesson → system prompt.

Проверяем, что дизлайки/лайки превращаются в «уроки» в памяти и
корректно попадают в system prompt через ContextAggregator.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret")

from app.db import (  # noqa: E402
    ConversationRepository,
    MemoryRepository,
    UserRepository,
    dispose_db,
    init_db,
    session_scope,
)
from app.services import memory as memory_pkg  # noqa: E402
from app.services.feedback_learner import (  # noqa: E402
    _format_lesson,
    _truncate,
    record_lesson,
)


@pytest.fixture(autouse=True)
async def _fresh_db():
    await init_db()
    memory_pkg.reset_default_memory()
    yield
    await dispose_db()
    memory_pkg.reset_default_memory()


# ======== Pure helpers ========


def test_truncate_short() -> None:
    assert _truncate("hello") == "hello"


def test_truncate_long() -> None:
    s = "a" * 300
    out = _truncate(s, limit=50)
    assert len(out) == 50
    assert out.endswith("…")


def test_truncate_strips_newlines() -> None:
    assert _truncate("hello\nworld") == "hello world"


def test_format_lesson_negative() -> None:
    lesson = _format_lesson(
        score=-1,
        user_msg="как дела?",
        assistant_msg="у меня нет чувств",
        note="слишком сухо",
    )
    assert "❌" in lesson
    assert "АНТИ-ПАТТЕРН" in lesson
    assert "как дела" in lesson
    assert "нет чувств" in lesson
    assert "слишком сухо" in lesson


def test_format_lesson_positive() -> None:
    lesson = _format_lesson(
        score=1,
        user_msg="расскажи анекдот",
        assistant_msg="почему программисты путают Хэллоуин и Рождество?",
        note=None,
    )
    assert "✅" in lesson
    assert "ХОРОШИЙ ПРИМЕР" in lesson


# ======== record_lesson integration ========


async def test_record_lesson_negative_creates_memory() -> None:
    async with session_scope() as session:
        await UserRepository(session).create("u1", "alice", "a@x.com", "h")
        convos = ConversationRepository(session)
        await convos.add("u1", "user", "что ты думаешь?")
        msg_id = await convos.add("u1", "assistant", "нет мнения")

    ok = await record_lesson(
        user_id="u1",
        message_id=msg_id,
        score=-1,
        note="слишком уклончиво",
    )
    assert ok is True

    async with session_scope() as session:
        lessons = await MemoryRepository(session).list_by_kind("u1", "lesson")

    assert len(lessons) == 1
    row = lessons[0]
    assert "❌" in row.text
    assert "нет мнения" in row.text
    assert "уклончиво" in row.text
    assert row.kind == "lesson"


async def test_record_lesson_positive_creates_memory() -> None:
    async with session_scope() as session:
        await UserRepository(session).create("u1", "alice", "a@x.com", "h")
        convos = ConversationRepository(session)
        await convos.add("u1", "user", "шутку!")
        msg_id = await convos.add("u1", "assistant", "два программиста в баре…")

    ok = await record_lesson(user_id="u1", message_id=msg_id, score=1)
    assert ok is True

    async with session_scope() as session:
        lessons = await MemoryRepository(session).list_by_kind("u1", "lesson")

    assert len(lessons) == 1
    assert "✅" in lessons[0].text


async def test_record_lesson_zero_score_ignored() -> None:
    ok = await record_lesson(user_id="u1", message_id=1, score=0)
    assert ok is False


async def test_record_lesson_no_message_no_note_returns_false() -> None:
    async with session_scope() as session:
        await UserRepository(session).create("u1", "alice", "a@x.com", "h")

    ok = await record_lesson(user_id="u1", message_id=9999, score=-1)
    assert ok is False


async def test_record_lesson_without_message_id_but_with_note() -> None:
    async with session_scope() as session:
        await UserRepository(session).create("u1", "alice", "a@x.com", "h")

    ok = await record_lesson(
        user_id="u1",
        message_id=None,
        score=-1,
        note="вообще не трогай политику",
    )
    assert ok is True

    async with session_scope() as session:
        lessons = await MemoryRepository(session).list_by_kind("u1", "lesson")
    assert len(lessons) == 1
    assert "политику" in lessons[0].text


# ======== list_by_kind repo ========


async def test_list_by_kind_filters_correctly() -> None:
    from app.services.memory import MemoryRecord, default_memory

    async with session_scope() as session:
        await UserRepository(session).create("u1", "alice", "a@x.com", "h")

    store = default_memory()
    await store.add(
        [
            MemoryRecord(id="", text="обычное сообщение", user_id="u1", metadata={}),
            MemoryRecord(id="", text="факт 1", user_id="u1", metadata={"kind": "fact"}),
            MemoryRecord(
                id="", text="урок 1", user_id="u1", metadata={"kind": "lesson"}
            ),
            MemoryRecord(
                id="", text="урок 2", user_id="u1", metadata={"kind": "lesson"}
            ),
        ]
    )

    async with session_scope() as session:
        lessons = await MemoryRepository(session).list_by_kind("u1", "lesson")
        facts = await MemoryRepository(session).list_by_kind("u1", "fact")

    assert len(lessons) == 2
    assert {l.text for l in lessons} == {"урок 1", "урок 2"}
    assert len(facts) == 1
    assert facts[0].text == "факт 1"


# ======== ContextAggregator integration ========


async def test_context_aggregator_includes_lessons_in_prompt() -> None:
    from app.services.context import ContextAggregator
    from app.services.emotion import EmotionService

    async with session_scope() as session:
        await UserRepository(session).create("u1", "alice", "a@x.com", "h")
        convos = ConversationRepository(session)
        await convos.add("u1", "user", "как дела?")
        msg_id = await convos.add("u1", "assistant", "у меня нет чувств")

    # Создаём урок через learner
    await record_lesson(
        user_id="u1",
        message_id=msg_id,
        score=-1,
        note="слишком сухо",
    )

    async with session_scope() as session:
        aggregator = ContextAggregator(session, emotion_service=EmotionService())
        ctx = await aggregator.get_full_context("u1", "поговорим ещё")
        assert len(ctx.lessons) >= 1
        assert any("АНТИ-ПАТТЕРН" in l for l in ctx.lessons)

        prompt = ContextAggregator.format_for_prompt(ctx, "ты Фреди")
        assert "УРОКИ ОТ ПОЛЬЗОВАТЕЛЯ" in prompt
        assert "❌" in prompt
        assert "Избегай стиля" in prompt
