"""SQL-backed VectorStore с recency + diversity (MMR-style).

Sprint 4: добавлен MMR-style ранкинг — после top-k по релевантности
выбираются ТОЛЬКО разнообразные записи (penalty за схожесть с уже
выбранными). Это исключает повторы вроде «я люблю кофе» × 5 в recall.

Формула: λ * relevance - (1 - λ) * max_similarity_to_selected
λ = 0.7 (баланс релевантности и разнообразия).
"""

from __future__ import annotations

import json
import math
import uuid
from datetime import datetime

from app.db import MemoryRepository, session_scope

from .base import Embedder, MemoryRecord
from .cache import CachedEmbedder


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _recency_score(created_at: datetime | None, half_life_days: float = 14) -> float:
    if created_at is None:
        return 0.5
    try:
        age_days = max(0.0, (datetime.utcnow() - created_at).total_seconds() / 86400)
    except Exception:
        return 0.5
    return math.exp(-age_days / half_life_days)


def _mmr_select(
    candidates: list[MemoryRecord],
    top_k: int,
    diversity_lambda: float = 0.7,
) -> list[MemoryRecord]:
    """Maximal Marginal Relevance: выбираем top_k разнообразных кандидатов."""
    if len(candidates) <= top_k:
        return candidates

    selected: list[MemoryRecord] = []
    pool = list(candidates)

    while pool and len(selected) < top_k:
        best_idx = 0
        best_score = float("-inf")
        for i, cand in enumerate(pool):
            if not selected:
                score = cand.score
            else:
                max_sim = max(
                    _cosine(cand.embedding or [], s.embedding or []) for s in selected
                )
                score = diversity_lambda * cand.score - (1 - diversity_lambda) * max_sim
            if score > best_score:
                best_score = score
                best_idx = i
        selected.append(pool.pop(best_idx))

    return selected


class SQLVectorStore:
    """VectorStore поверх таблицы `fr_memories` с recency + MMR diversity."""

    RECENCY_WEIGHT = 0.25
    FACT_BOOST = 0.05
    MMR_LAMBDA = 0.7

    def __init__(self, embedder: Embedder, *, cache_capacity: int = 512) -> None:
        # Автоматически оборачиваем в LRU-кеш
        self.embedder = (
            embedder if isinstance(embedder, CachedEmbedder) else CachedEmbedder(embedder, capacity=cache_capacity)
        )

    async def add(self, records: list[MemoryRecord]) -> None:
        if not records:
            return
        to_embed = [r for r in records if r.embedding is None]
        if to_embed:
            vectors = await self.embedder.embed([r.text for r in to_embed])
            for r, v in zip(to_embed, vectors, strict=True):
                r.embedding = v
        async with session_scope() as session:
            repo = MemoryRepository(session)
            for r in records:
                if not r.id:
                    r.id = uuid.uuid4().hex
                await repo.add(
                    user_id=r.user_id or "",
                    text=r.text,
                    embedding=r.embedding or [],
                    kind=str(r.metadata.get("kind", "message")),
                    metadata=r.metadata,
                )

    async def search(
        self,
        query: str,
        *,
        user_id: str | None = None,
        top_k: int = 5,
        diversity: bool = True,
    ) -> list[MemoryRecord]:
        if not user_id:
            return []
        query_vec = (await self.embedder.embed([query]))[0]
        async with session_scope() as session:
            rows = await MemoryRepository(session).list_for_user(user_id)

        scored: list[MemoryRecord] = []
        for row in rows:
            try:
                vec = json.loads(row.embedding)
            except Exception:
                continue
            cosine = _cosine(query_vec, vec)
            recency = _recency_score(row.created_at)
            base = cosine * (1 - self.RECENCY_WEIGHT) + recency * self.RECENCY_WEIGHT
            if (row.kind or "") == "fact":
                base += self.FACT_BOOST
            scored.append(
                MemoryRecord(
                    id=str(row.id),
                    text=row.text,
                    user_id=row.user_id,
                    metadata=json.loads(row.extra_metadata or "{}"),
                    embedding=vec,
                    score=base,
                )
            )
        scored.sort(key=lambda r: r.score, reverse=True)

        # Берём расширенный пул, чтобы MMR имел из чего выбирать
        if diversity and len(scored) > top_k:
            pool = scored[: max(top_k * 3, 15)]
            return _mmr_select(pool, top_k, self.MMR_LAMBDA)

        return scored[:top_k]

    async def delete_user(self, user_id: str) -> int:
        async with session_scope() as session:
            return await MemoryRepository(session).delete_user(user_id)

    async def forget(self, user_id: str, query: str) -> int:
        async with session_scope() as session:
            return await MemoryRepository(session).delete_by_text_match(user_id, query)

    def cache_stats(self) -> dict:
        if isinstance(self.embedder, CachedEmbedder):
            return self.embedder.stats()
        return {}
