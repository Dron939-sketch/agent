"""Memory-слой Фреди: embeddings, vector stores, summarization.

Фабрика `default_memory()` возвращает готовое к работе in-memory хранилище
поверх `default_embedder()`. В Фазе 2 PR4 будет добавлен Qdrant-адаптер.
"""

from .base import Embedder, MemoryRecord, VectorStore
from .embeddings import HashEmbedder, OpenAIEmbedder, default_embedder
from .inmemory import InMemoryVectorStore
from .summarizer import summarize_messages

_store: InMemoryVectorStore | None = None


def default_memory() -> InMemoryVectorStore:
    global _store
    if _store is None:
        _store = InMemoryVectorStore(default_embedder())
    return _store


__all__ = [
    "MemoryRecord",
    "Embedder",
    "VectorStore",
    "HashEmbedder",
    "OpenAIEmbedder",
    "default_embedder",
    "InMemoryVectorStore",
    "default_memory",
    "summarize_messages",
]
