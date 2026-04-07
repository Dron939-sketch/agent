"""Адаптеры OpenAI-совместимых API (DeepSeek, OpenAI, локальные совместимые серверы)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import aiohttp

from app.core.logging import get_logger

from .base import ChatMessage, ChatResponse, LLMError, Usage

logger = get_logger(__name__)


class OpenAICompatibleClient:
    """База для всех провайдеров с OpenAI-совместимым chat completions API."""

    name: str = "openai-compatible"

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str,
        model: str,
        timeout: int = 60,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _payload(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float,
        max_tokens: int,
        stream: bool,
    ) -> dict[str, Any]:
        return {
            "model": self.model,
            "messages": [m.to_openai() for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
        }

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> ChatResponse:
        if not self.api_key:
            raise LLMError(f"{self.name}: missing api key")
        url = f"{self.base_url}/chat/completions"
        payload = self._payload(messages, temperature=temperature, max_tokens=max_tokens, stream=False)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, headers=self._headers(), json=payload, timeout=self.timeout
                ) as resp:
                    body = await resp.text()
                    if resp.status != 200:
                        raise LLMError(f"{self.name} {resp.status}: {body[:300]}")
                    data = json.loads(body)
        except aiohttp.ClientError as exc:
            raise LLMError(f"{self.name} network error: {exc}") from exc

        text = data["choices"][0]["message"]["content"]
        usage_raw = data.get("usage") or {}
        return ChatResponse(
            text=text,
            model=self.model,
            usage=Usage(
                prompt_tokens=usage_raw.get("prompt_tokens", 0),
                completion_tokens=usage_raw.get("completion_tokens", 0),
                total_tokens=usage_raw.get("total_tokens", 0),
            ),
            raw=data,
        )

    async def stream(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> AsyncIterator[str]:
        if not self.api_key:
            raise LLMError(f"{self.name}: missing api key")
        url = f"{self.base_url}/chat/completions"
        payload = self._payload(messages, temperature=temperature, max_tokens=max_tokens, stream=True)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, headers=self._headers(), json=payload, timeout=self.timeout
                ) as resp:
                    if resp.status != 200:
                        body = await resp.text()
                        raise LLMError(f"{self.name} {resp.status}: {body[:300]}")
                    async for raw_line in resp.content:
                        line = raw_line.decode("utf-8", errors="ignore").strip()
                        if not line or not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        delta = chunk["choices"][0].get("delta", {}).get("content")
                        if delta:
                            yield delta
        except aiohttp.ClientError as exc:
            raise LLMError(f"{self.name} stream error: {exc}") from exc
