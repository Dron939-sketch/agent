"""Anthropic Claude-адаптер (Messages API).

Конвертирует наш `ChatMessage` в формат Anthropic (system отдельным полем).
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import aiohttp

from app.core.config import Config
from app.core.logging import get_logger

from .base import ChatMessage, ChatResponse, LLMError, Usage

logger = get_logger(__name__)

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"


class AnthropicClient:
    name = "anthropic"

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "claude-sonnet-4-6",
        timeout: int = 60,
    ) -> None:
        self.api_key = api_key if api_key is not None else Config.ANTHROPIC_API_KEY
        self.model = model
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self.api_key,
            "anthropic-version": API_VERSION,
            "content-type": "application/json",
        }

    def _split(self, messages: list[ChatMessage]) -> tuple[str | None, list[dict[str, Any]]]:
        system_parts: list[str] = []
        out: list[dict[str, Any]] = []
        for m in messages:
            if m.role == "system":
                system_parts.append(m.content)
                continue
            role = "assistant" if m.role == "assistant" else "user"
            out.append({"role": role, "content": m.content})
        system = "\n\n".join(system_parts) if system_parts else None
        return system, out

    def _payload(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float,
        max_tokens: int,
        stream: bool,
    ) -> dict[str, Any]:
        system, msgs = self._split(messages)
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": msgs,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": stream,
        }
        if system:
            payload["system"] = system
        return payload

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> ChatResponse:
        if not self.api_key:
            raise LLMError("anthropic: missing api key")
        payload = self._payload(messages, temperature=temperature, max_tokens=max_tokens, stream=False)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    API_URL, headers=self._headers(), json=payload, timeout=self.timeout
                ) as resp:
                    body = await resp.text()
                    if resp.status != 200:
                        raise LLMError(f"anthropic {resp.status}: {body[:300]}")
                    data = json.loads(body)
        except aiohttp.ClientError as exc:
            raise LLMError(f"anthropic network error: {exc}") from exc

        text_parts = [
            block.get("text", "") for block in data.get("content", []) if block.get("type") == "text"
        ]
        usage_raw = data.get("usage") or {}
        return ChatResponse(
            text="".join(text_parts),
            model=self.model,
            usage=Usage(
                prompt_tokens=usage_raw.get("input_tokens", 0),
                completion_tokens=usage_raw.get("output_tokens", 0),
                total_tokens=usage_raw.get("input_tokens", 0) + usage_raw.get("output_tokens", 0),
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
            raise LLMError("anthropic: missing api key")
        payload = self._payload(messages, temperature=temperature, max_tokens=max_tokens, stream=True)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    API_URL, headers=self._headers(), json=payload, timeout=self.timeout
                ) as resp:
                    if resp.status != 200:
                        body = await resp.text()
                        raise LLMError(f"anthropic {resp.status}: {body[:300]}")
                    async for raw_line in resp.content:
                        line = raw_line.decode("utf-8", errors="ignore").strip()
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        try:
                            event = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        if event.get("type") == "content_block_delta":
                            delta = event.get("delta", {}).get("text")
                            if delta:
                                yield delta
                        elif event.get("type") == "message_stop":
                            break
        except aiohttp.ClientError as exc:
            raise LLMError(f"anthropic stream error: {exc}") from exc
