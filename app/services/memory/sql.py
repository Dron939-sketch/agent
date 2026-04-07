"""SQL-backed VectorStore с recency-weighted ranking.

Sprint 1: добавлен `recency_weight` — недавние воспоминания получают
бонус к cosine similarity. Это снимает ситуацию, когда модель цепляется
за старый факт вместо более актуального.

Формула: final = cosine * (1 - λ) + recency * λ
где `λ = 0.25`, `recency = exp(-age_days / half_life)`, `half_life = 14 дней`.

Также `kind=fact` получает +0.05 буст — экстрагированные факты ценнее
сырых сообщений.
"""

from __future__ import annotations

import json
import math
import uuid
from datetime import datetime

from app.db import MemoryRepository, session_scope

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


def _recency_score(created_at: datetime | None, half_life_days: float = 14) -> float:
    """Экспоненциальный затух: 1.0 сейчас, 0.5 через 14 дней."""
    if created_at is None:
        return 0.5
    try:
        age_days = max(0.0, (datetime.utcnow() - created_at).total_seconds() / 86400)
    except Exception:
        return 0.5
    return math.exp(-age_days / half_life_days)


class SQLVectorStore:
    """VectorStore поверх таблицы `fr_memories` с recency-aware scoring."""

    RECENCY_WEIGHT = 0.25
    FACT_BOOST = 0.05

    def __init__(self, embedder: Embedder) -> None:
        self.embedder = embedder

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
        return scored[:top_k]

    async def delete_user(self, user_id: str) -> int:
        async with session_scope() as session:
            return await MemoryRepository(session).delete_user(user_id)

    async def forget(self, user_id: str, query: str) -> int:
        """Удаляет все memory-записи пользователя, содержащие подстроку."""
        async with session_scope() as session:
            return await MemoryRepository(session).delete_by_text_match(user_id, query)
