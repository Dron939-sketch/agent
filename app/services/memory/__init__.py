"""Memory-слой Фреди: embeddings, vector stores (in-memory / SQL / Qdrant), summarization.

`default_memory()` возвращает SQL-store как дефолт (персистентный, без новых
зависимостей). Для in-memory варианта используйте `InMemoryVectorStore`.
"""

from .base import Embedder, MemoryRecord, VectorStore
from .embeddings import HashEmbedder, OpenAIEmbedder, default_embedder
from .inmemory import InMemoryVectorStore
from .sql import SQLVectorStore
from .summarizer import summarize_messages

_store: SQLVectorStore | None = None


def default_memory() -> SQLVectorStore:
    global _store
    if _store is None:
        _store = SQLVectorStore(default_embedder())
    return _store


def reset_default_memory() -> None:
    """Сброс синглтона (для тестов)."""
    global _store
    _store = None


__all__ = [
    "MemoryRecord",
    "Embedder",
    "VectorStore",
    "HashEmbedder",
    "OpenAIEmbedder",
    "default_embedder",
    "InMemoryVectorStore",
    "SQLVectorStore",
    "default_memory",
    "reset_default_memory",
    "summarize_messages",
]
