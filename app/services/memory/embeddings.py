"""Эмбеддеры: детерминированный hash-fallback и опциональный OpenAI.

`HashEmbedder` не требует сетевых вызовов, не идеален по качеству, но даёт
работающую семантику для тестов и CI без новых зависимостей. Когда задана
`OPENAI_API_KEY`, фабрика `default_embedder()` отдаст `OpenAIEmbedder`.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Any

import aiohttp

from app.core.config import Config
from app.core.logging import get_logger

from .base import Embedder

logger = get_logger(__name__)

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text)]


class HashEmbedder:
    """Хеш-эмбеддер: токенизирует, разбрасывает токены по `dim` бинам."""

    name = "hash"

    def __init__(self, dim: int = 256) -> None:
        self.dim = dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            vec = [0.0] * self.dim
            for token in _tokenize(text):
                idx = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16) % self.dim
                sign = 1.0 if (idx & 1) == 0 else -1.0
                vec[idx] += sign
            norm = math.sqrt(sum(x * x for x in vec)) or 1.0
            out.append([x / norm for x in vec])
        return out


class OpenAIEmbedder:
    """OpenAI text-embedding-3-small (1536 dim)."""

    name = "openai"
    api_url = "https://api.openai.com/v1/embeddings"

    def __init__(self, api_key: str | None = None, model: str = "text-embedding-3-small") -> None:
        self.api_key = api_key or Config.OPENAI_API_KEY
        self.model = model
        self.dim = 1536

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not self.api_key:
            raise RuntimeError("OpenAIEmbedder requires OPENAI_API_KEY")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {"model": self.model, "input": texts}
        async with aiohttp.ClientSession() as session:
            async with session.post(self.api_url, headers=headers, json=payload, timeout=30) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    raise RuntimeError(f"openai embed {resp.status}: {body[:300]}")
                data = await resp.json()
                return [row["embedding"] for row in data["data"]]


def default_embedder() -> Embedder:
    if Config.OPENAI_API_KEY:
        return OpenAIEmbedder()
    return HashEmbedder()
