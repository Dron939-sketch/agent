"""Опциональный Qdrant-адаптер.

Импорт `qdrant_client` отложен — модуль валиден без него, но при попытке
создать клиент без установленного пакета бросает понятную ошибку.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.core.config import Config

from .base import Embedder, MemoryRecord


class QdrantVectorStore:
    """VectorStore над Qdrant. Требует `qdrant-client` (опциональная зависимость)."""

    def __init__(
        self,
        embedder: Embedder,
        *,
        url: str | None = None,
        collection: str = "freddy_memories",
    ) -> None:
        try:
            from qdrant_client import AsyncQdrantClient  # type: ignore
            from qdrant_client.http import models as qmodels  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "qdrant-client is not installed. `pip install qdrant-client`"
            ) from exc

        self._qmodels = qmodels
        self.embedder = embedder
        self.collection = collection
        self.client = AsyncQdrantClient(url=url or Config.QDRANT_URL)

    async def ensure_collection(self) -> None:
        existing = await self.client.get_collections()
        names = {c.name for c in existing.collections}
        if self.collection in names:
            return
        await self.client.create_collection(
            collection_name=self.collection,
            vectors_config=self._qmodels.VectorParams(
                size=self.embedder.dim,
                distance=self._qmodels.Distance.COSINE,
            ),
        )

    async def add(self, records: list[MemoryRecord]) -> None:
        if not records:
            return
        await self.ensure_collection()
        to_embed = [r for r in records if r.embedding is None]
        if to_embed:
            vectors = await self.embedder.embed([r.text for r in to_embed])
            for r, v in zip(to_embed, vectors, strict=True):
                r.embedding = v

        points = []
        for r in records:
            if not r.id:
                r.id = uuid.uuid4().hex
            payload: dict[str, Any] = {
                "text": r.text,
                "user_id": r.user_id or "",
                **(r.metadata or {}),
            }
            points.append(
                self._qmodels.PointStruct(id=r.id, vector=r.embedding or [], payload=payload)
            )
        await self.client.upsert(collection_name=self.collection, points=points)

    async def search(
        self,
        query: str,
        *,
        user_id: str | None = None,
        top_k: int = 5,
    ) -> list[MemoryRecord]:
        await self.ensure_collection()
        query_vec = (await self.embedder.embed([query]))[0]
        flt = None
        if user_id:
            flt = self._qmodels.Filter(
                must=[
                    self._qmodels.FieldCondition(
                        key="user_id",
                        match=self._qmodels.MatchValue(value=user_id),
                    )
                ]
            )
        hits = await self.client.search(
            collection_name=self.collection,
            query_vector=query_vec,
            limit=top_k,
            query_filter=flt,
        )
        out: list[MemoryRecord] = []
        for h in hits:
            payload = h.payload or {}
            out.append(
                MemoryRecord(
                    id=str(h.id),
                    text=payload.get("text", ""),
                    user_id=payload.get("user_id"),
                    metadata={k: v for k, v in payload.items() if k not in ("text", "user_id")},
                    score=h.score or 0.0,
                )
            )
        return out

    async def delete_user(self, user_id: str) -> int:
        await self.ensure_collection()
        flt = self._qmodels.Filter(
            must=[
                self._qmodels.FieldCondition(
                    key="user_id",
                    match=self._qmodels.MatchValue(value=user_id),
                )
            ]
        )
        await self.client.delete(
            collection_name=self.collection,
            points_selector=self._qmodels.FilterSelector(filter=flt),
        )
        return 0  # Qdrant не возвращает count напрямую
