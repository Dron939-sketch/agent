"""Ollama-адаптер для локальных моделей (llama, qwen, mistral и т.д.)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import aiohttp

from app.core.config import Config
from app.core.logging import get_logger

from .base import ChatMessage, ChatResponse, LLMError, Usage

logger = get_logger(__name__)


class OllamaClient:
    name = "ollama"

    def __init__(
        self,
        base_url: str | None = None,
        model: str = "llama3.2",
        timeout: int = 120,
    ) -> None:
        self.base_url = (base_url or Config.OLLAMA_BASE_URL).rstrip("/")
        self.model = model
        self.timeout = timeout

    def _payload(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float,
        stream: bool,
    ) -> dict[str, Any]:
        return {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "options": {"temperature": temperature},
            "stream": stream,
        }

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int = 2000,  # noqa: ARG002 - ollama игнорирует, но интерфейс единый
    ) -> ChatResponse:
        url = f"{self.base_url}/api/chat"
        payload = self._payload(messages, temperature=temperature, stream=False)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=self.timeout) as resp:
                    body = await resp.text()
                    if resp.status != 200:
                        raise LLMError(f"ollama {resp.status}: {body[:300]}")
                    data = json.loads(body)
        except aiohttp.ClientError as exc:
            raise LLMError(f"ollama network error: {exc}") from exc

        return ChatResponse(
            text=data.get("message", {}).get("content", ""),
            model=self.model,
            usage=Usage(),
            raw=data,
        )

    async def stream(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int = 2000,  # noqa: ARG002
    ) -> AsyncIterator[str]:
        url = f"{self.base_url}/api/chat"
        payload = self._payload(messages, temperature=temperature, stream=True)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=self.timeout) as resp:
                    if resp.status != 200:
                        body = await resp.text()
                        raise LLMError(f"ollama {resp.status}: {body[:300]}")
                    async for raw_line in resp.content:
                        line = raw_line.decode("utf-8", errors="ignore").strip()
                        if not line:
                            continue
                        try:
                            chunk = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        delta = chunk.get("message", {}).get("content")
                        if delta:
                            yield delta
                        if chunk.get("done"):
                            break
        except aiohttp.ClientError as exc:
            raise LLMError(f"ollama stream error: {exc}") from exc
