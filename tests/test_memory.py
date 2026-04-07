"""Тесты memory: HashEmbedder, in-memory store, summarizer."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from app.services.llm import ChatMessage, ChatResponse, LLMRouter, Usage
from app.services.memory import (
    HashEmbedder,
    InMemoryVectorStore,
    MemoryRecord,
    summarize_messages,
)


@pytest.mark.asyncio
async def test_hash_embedder_dim_and_normalisation() -> None:
    emb = HashEmbedder(dim=64)
    vectors = await emb.embed(["привет мир", "hello world"])
    assert len(vectors) == 2
    assert all(len(v) == 64 for v in vectors)
    # норма ~1
    for v in vectors:
        norm = sum(x * x for x in v) ** 0.5
        assert 0.99 <= norm <= 1.01


@pytest.mark.asyncio
async def test_inmemory_store_topk_and_isolation() -> None:
    store = InMemoryVectorStore(HashEmbedder(dim=128))
    await store.add(
        [
            MemoryRecord(id="", text="Я люблю Python и SQLAlchemy", user_id="alice"),
            MemoryRecord(id="", text="Завтра встреча с инвесторами", user_id="alice"),
            MemoryRecord(id="", text="Купить молоко и хлеб", user_id="alice"),
            MemoryRecord(id="", text="Конфиденциальные заметки Боба", user_id="bob"),
        ]
    )

    hits = await store.search("python sqlalchemy", user_id="alice", top_k=2)
    assert len(hits) == 2
    assert "Python" in hits[0].text
    assert hits[0].score >= hits[1].score

    # изоляция между пользователями
    bob_hits = await store.search("python", user_id="bob", top_k=5)
    assert all(r.user_id == "bob" for r in bob_hits)
    assert not any("Python" in r.text for r in bob_hits)

    # удаление по пользователю
    removed = await store.delete_user("alice")
    assert removed == 3
    assert await store.search("python", user_id="alice") == []


class _FakeSummaryClient:
    name = "fake"
    model = "fake-1"

    async def chat(self, messages, *, temperature=0.7, max_tokens=2000):
        # эмулирует «компрессор»: возвращает первые 80 символов user-сообщения
        user_text = next(m.content for m in messages if m.role == "user")
        return ChatResponse(text=f"СВОДКА: {user_text[:80]}", model=self.model, usage=Usage())

    async def stream(self, messages, *, temperature=0.7, max_tokens=2000) -> AsyncIterator[str]:
        if False:
            yield ""


@pytest.mark.asyncio
async def test_summarizer_uses_router() -> None:
    router = LLMRouter(profiles={"fast": [_FakeSummaryClient()]})
    out = await summarize_messages(
        router,
        [
            {"role": "user", "content": "Хочу запустить стартап про AI-помощника"},
            {"role": "assistant", "content": "Отлично, давай обсудим план"},
            {"role": "user", "content": "Бюджет 1млн рублей"},
        ],
        profile="fast",
    )
    assert out.startswith("СВОДКА:")
    assert "user" in out
