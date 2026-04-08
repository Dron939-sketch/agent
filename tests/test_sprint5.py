"""Sprint 5 tests: SentenceBuffer, consolidator, notifications composer."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret")

from app.db import dispose_db, init_db, session_scope  # noqa: E402
from app.services.llm.sentences import SentenceBuffer, stream_with_sentences  # noqa: E402
from app.services.memory import HashEmbedder, MemoryRecord, SQLVectorStore, reset_default_memory  # noqa: E402
from app.services.memory.consolidator import consolidate_user  # noqa: E402


# ======== SentenceBuffer ========


def test_sentence_buffer_basic() -> None:
    buf = SentenceBuffer()
    assert buf.add("Hello") == []
    assert buf.add(" world") == []
    sentences = buf.add(". Next sentence. ")
    # Обе фразы должны вычлениться
    assert len(sentences) == 2
    assert "Hello world." in sentences[0]
    assert "Next sentence." in sentences[1]


def test_sentence_buffer_multiple_in_one_chunk() -> None:
    buf = SentenceBuffer()
    sentences = buf.add("First. Second! Third? ")
    assert len(sentences) == 3
    assert "First." in sentences[0]
    assert "Second!" in sentences[1]
    assert "Third?" in sentences[2]


def test_sentence_buffer_flush_tail() -> None:
    buf = SentenceBuffer()
    buf.add("Без точки в конце")
    tail = buf.flush()
    assert tail == "Без точки в конце"
    assert buf.flush() is None


def test_sentence_buffer_with_ellipsis() -> None:
    buf = SentenceBuffer()
    sentences = buf.add("Понимаешь… это сложно. ")
    assert len(sentences) >= 1


@pytest.mark.asyncio
async def test_stream_with_sentences_async() -> None:
    async def chunks():
        for c in ["Привет", " мир", ". Как ", "дела?"]:
            yield c

    events = []
    async for ev in stream_with_sentences(chunks()):
        events.append(ev)

    tokens = [e for e in events if e[0] == "token"]
    assert len(tokens) == 4
    all_text = " ".join(t[1] for t in events if t[0] in ("sentence", "final"))
    assert "дела" in all_text


# ======== Memory consolidator ========


@pytest.mark.asyncio
async def test_consolidator_dedup_and_junk() -> None:
    await init_db()
    reset_default_memory()
    try:
        store = SQLVectorStore(HashEmbedder(dim=64))
        await store.add(
            [
                MemoryRecord(id="", text="Я люблю Python", user_id="u1"),
                MemoryRecord(id="", text="Я люблю Python", user_id="u1"),  # дубликат
                MemoryRecord(id="", text="Я работаю программистом", user_id="u1"),
                MemoryRecord(id="", text="ok", user_id="u1"),  # junk (короткий)
            ]
        )

        stats = await consolidate_user("u1", dedup_threshold=0.9)
        assert stats["junk_removed"] == 1
        assert stats["dedup_removed"] >= 1
        assert stats["total_after"] <= 2
    finally:
        await dispose_db()
        reset_default_memory()


@pytest.mark.asyncio
async def test_consolidator_keeps_facts_over_messages() -> None:
    await init_db()
    reset_default_memory()
    try:
        store = SQLVectorStore(HashEmbedder(dim=64))
        await store.add(
            [
                MemoryRecord(
                    id="",
                    text="Меня зовут Андрей и я работаю программистом",
                    user_id="u1",
                    metadata={"kind": "fact"},
                ),
                MemoryRecord(
                    id="",
                    text="Меня зовут Андрей и я работаю программистом",
                    user_id="u1",
                    metadata={"kind": "message"},
                ),
            ]
        )
        stats = await consolidate_user("u1")
        assert stats["dedup_removed"] == 1
        async with session_scope() as session:
            from app.db import MemoryRepository

            rows = await MemoryRepository(session).list_for_user("u1")
        assert len(rows) == 1
        assert rows[0].kind == "fact"
    finally:
        await dispose_db()
        reset_default_memory()
