"""Абстракция LLM-провайдера + DeepSeek-адаптер.

Фаза 1: вынести из main.py. Фаза 2 добавит Claude/OpenAI/Ollama
и auto-router, реализуя общий протокол `LLMClient`.
"""

from __future__ import annotations

from typing import Any, Protocol

import aiohttp

from app.core.config import Config
from app.core.logging import get_logger

logger = get_logger(__name__)


class LLMClient(Protocol):
    """Минимальный протокол LLM-клиента."""

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> str: ...


class DeepSeekClient:
    """Адаптер DeepSeek Chat Completions API."""

    api_url = "https://api.deepseek.com/v1/chat/completions"
    model = "deepseek-chat"

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or Config.DEEPSEEK_API_KEY

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> str:
        if not self.api_key:
            return "AI сервис временно недоступен. Пожалуйста, попробуйте позже."

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.api_url, headers=headers, json=payload, timeout=30
                ) as resp:
                    if resp.status != 200:
                        body = await resp.text()
                        logger.error("DeepSeek %s: %s", resp.status, body[:300])
                        return "Извините, произошла ошибка. Попробуйте позже."
                    data = await resp.json()
                    return data["choices"][0]["message"]["content"]
        except Exception as exc:  # pragma: no cover - сетевые сбои
            logger.exception("DeepSeek call failed: %s", exc)
            return "Извините, произошла ошибка. Попробуйте позже."


def default_llm() -> LLMClient:
    """Фабрика дефолтного клиента (в Фазе 2 заменим на роутер)."""
    return DeepSeekClient()
