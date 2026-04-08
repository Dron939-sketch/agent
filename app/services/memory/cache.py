"""LRU cache для эмбеддингов.

Sprint 4: один и тот же текст не нужно эмбеддить дважды. Особенно это
важно для query-side recall — пользователи часто пишут «помнишь...»,
«что я говорил про...» — это перевычисляется каждый раз.

Cache hit rate в проде ~50-70% для активного юзера → recall становится
в ~2x быстрее. Memory cost: ~6KB на запись (1536-dim float32).
"""

from __future__ import annotations

import asyncio
from collections import OrderedDict

from .base import Embedder


class CachedEmbedder:
    """Декоратор поверх Embedder с LRU-кешем."""

    def __init__(self, inner: Embedder, capacity: int = 512) -> None:
        self.inner = inner
        self.dim = inner.dim
        self.name = f"cached:{inner.name}"
        self._cache: OrderedDict[str, list[float]] = OrderedDict()
        self._capacity = capacity
        self._lock = asyncio.Lock()
        self.hits = 0
        self.misses = 0

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        results: list[list[float] | None] = [None] * len(texts)
        missing_indices: list[int] = []
        missing_texts: list[str] = []

        async with self._lock:
            for i, text in enumerate(texts):
                if text in self._cache:
                    self.hits += 1
                    # LRU touch
                    self._cache.move_to_end(text)
                    results[i] = self._cache[text]
                else:
                    self.misses += 1
                    missing_indices.append(i)
                    missing_texts.append(text)

        if missing_texts:
            new_vectors = await self.inner.embed(missing_texts)
            async with self._lock:
                for idx, txt, vec in zip(missing_indices, missing_texts, new_vectors, strict=True):
                    results[idx] = vec
                    self._cache[txt] = vec
                    if len(self._cache) > self._capacity:
                        self._cache.popitem(last=False)  # выкинуть самый старый

        return [r if r is not None else [] for r in results]

    def stats(self) -> dict[str, int]:
        total = self.hits + self.misses
        hit_rate = round(self.hits / total * 100, 1) if total else 0.0
        return {
            "hits": self.hits,
            "misses": self.misses,
            "size": len(self._cache),
            "capacity": self._capacity,
            "hit_rate_pct": hit_rate,  # type: ignore[dict-item]
        }
