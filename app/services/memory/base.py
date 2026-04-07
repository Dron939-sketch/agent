"""Базовые типы и протоколы memory-слоя."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(slots=True)
class MemoryRecord:
    id: str
    text: str
    user_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    embedding: list[float] | None = None
    score: float = 0.0
    created_at: float = field(default_factory=time.time)


@runtime_checkable
class Embedder(Protocol):
    """Протокол векторизатора."""

    dim: int
    name: str

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


@runtime_checkable
class VectorStore(Protocol):
    """Протокол векторного хранилища."""

    async def add(self, records: list[MemoryRecord]) -> None: ...

    async def search(
        self,
        query: str,
        *,
        user_id: str | None = None,
        top_k: int = 5,
    ) -> list[MemoryRecord]: ...

    async def delete_user(self, user_id: str) -> int: ...
