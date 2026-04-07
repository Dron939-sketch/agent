"""In-memory векторное хранилище с косинусной близостью.

Подходит для тестов, dev-режима и небольших инсталляций. В Фазе 2 PR4
заменим/дополним адаптером Qdrant, сохранив тот же протокол `VectorStore`.
"""

from __future__ import annotations

import asyncio
import math
import uuid
from collections import defaultdict

from .base import Embedder, MemoryRecord


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


class InMemoryVectorStore:
    """Простое потокобезопасное хранилище: пер-пользовательский список записей."""

    def __init__(self, embedder: Embedder) -> None:
        self.embedder = embedder
        self._by_user: dict[str, list[MemoryRecord]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def add(self, records: list[MemoryRecord]) -> None:
        if not records:
            return
        to_embed = [r for r in records if r.embedding is None]
        if to_embed:
            vectors = await self.embedder.embed([r.text for r in to_embed])
            for r, v in zip(to_embed, vectors, strict=True):
                r.embedding = v
        async with self._lock:
            for r in records:
                if not r.id:
                    r.id = uuid.uuid4().hex
                self._by_user[r.user_id or ""].append(r)

    async def search(
        self,
        query: str,
        *,
        user_id: str | None = None,
        top_k: int = 5,
    ) -> list[MemoryRecord]:
        async with self._lock:
            pool = list(self._by_user.get(user_id or "", []))
        if not pool:
            return []
        query_vec = (await self.embedder.embed([query]))[0]
        scored: list[MemoryRecord] = []
        for record in pool:
            if record.embedding is None:
                continue
            score = _cosine(query_vec, record.embedding)
            scored.append(
                MemoryRecord(
                    id=record.id,
                    text=record.text,
                    user_id=record.user_id,
                    metadata=record.metadata,
                    embedding=record.embedding,
                    score=score,
                    created_at=record.created_at,
                )
            )
        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[:top_k]

    async def delete_user(self, user_id: str) -> int:
        async with self._lock:
            removed = len(self._by_user.get(user_id, []))
            self._by_user.pop(user_id, None)
            return removed
