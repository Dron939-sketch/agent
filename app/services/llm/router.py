"""LLM-роутер: профиль задачи → провайдер, fallback по списку.

Использование:
    router = LLMRouter.from_env()
    resp = await router.chat(messages, profile="smart")
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Literal

from app.core.config import Config
from app.core.logging import get_logger

from .anthropic import AnthropicClient
from .base import ChatMessage, ChatResponse, LLMClient, LLMError
from .deepseek import DeepSeekClient
from .ollama import OllamaClient
from .openai import OpenAIClient

logger = get_logger(__name__)

Profile = Literal["fast", "smart", "cheap", "local"]


@dataclass(slots=True)
class LLMRouter:
    """Маршрутизирует запросы по профилю и делает fallback по цепочке."""

    profiles: dict[str, list[LLMClient]] = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> "LLMRouter":
        """Собирает роутер из доступных провайдеров на основе env-ключей."""
        anthropic = AnthropicClient() if Config.ANTHROPIC_API_KEY else None
        openai_fast = OpenAIClient(model="gpt-4o-mini") if Config.OPENAI_API_KEY else None
        openai_smart = OpenAIClient(model="gpt-4o") if Config.OPENAI_API_KEY else None
        deepseek = DeepSeekClient() if Config.DEEPSEEK_API_KEY else None
        ollama = OllamaClient()  # локальный — всегда доступен как последний fallback

        smart_chain: list[LLMClient] = [
            c for c in (deepseek, anthropic, openai_smart, ollama) if c is not None
        ]
        fast_chain: list[LLMClient] = [
            c for c in (deepseek, openai_fast, anthropic, ollama) if c is not None
        ]
        cheap_chain: list[LLMClient] = [
            c for c in (deepseek, openai_fast, ollama) if c is not None
        ]
        local_chain: list[LLMClient] = [ollama]

        return cls(
            profiles={
                "smart": smart_chain or [ollama],
                "fast": fast_chain or [ollama],
                "cheap": cheap_chain or [ollama],
                "local": local_chain,
            }
        )

    def _chain(self, profile: Profile) -> list[LLMClient]:
        chain = self.profiles.get(profile)
        if not chain:
            raise LLMError(f"no providers for profile {profile!r}")
        return chain

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        profile: Profile = "smart",
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> ChatResponse:
        last_error: Exception | None = None
        for client in self._chain(profile):
            try:
                logger.info("LLM call profile=%s provider=%s", profile, client.name)
                return await client.chat(
                    messages, temperature=temperature, max_tokens=max_tokens
                )
            except LLMError as exc:
                logger.warning("Provider %s failed: %s — trying fallback", client.name, exc)
                last_error = exc
                continue
        raise LLMError(f"all providers failed for profile {profile}: {last_error}")

    async def stream(
        self,
        messages: list[ChatMessage],
        *,
        profile: Profile = "smart",
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> AsyncIterator[str]:
        """Стриминг от первого живого провайдера в цепочке."""
        last_error: Exception | None = None
        for client in self._chain(profile):
            try:
                logger.info("LLM stream profile=%s provider=%s", profile, client.name)
                async for chunk in client.stream(
                    messages, temperature=temperature, max_tokens=max_tokens
                ):
                    yield chunk
                return
            except LLMError as exc:
                logger.warning("Stream provider %s failed: %s", client.name, exc)
                last_error = exc
                continue
        raise LLMError(f"all stream providers failed for profile {profile}: {last_error}")
