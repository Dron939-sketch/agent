"""LLM-слой Фреди.

Публичный API:
    from app.services.llm import (
        ChatMessage, ChatResponse, LLMClient, LLMError,
        AnthropicClient, DeepSeekClient, OpenAIClient, OllamaClient,
        LLMRouter, default_llm,
    )
"""

from __future__ import annotations

from .anthropic import AnthropicClient
from .base import ChatMessage, ChatResponse, LLMClient, LLMError, Role, Usage
from .deepseek import DeepSeekClient
from .ollama import OllamaClient
from .openai import OpenAIClient
from .router import LLMRouter, Profile

_router: LLMRouter | None = None


def default_router() -> LLMRouter:
    """Singleton-роутер, собранный из env."""
    global _router
    if _router is None:
        _router = LLMRouter.from_env()
    return _router


def default_llm() -> LLMRouter:
    """Backward-compat фабрика (старое имя из Фазы 1)."""
    return default_router()


__all__ = [
    "ChatMessage",
    "ChatResponse",
    "Usage",
    "Role",
    "LLMClient",
    "LLMError",
    "AnthropicClient",
    "DeepSeekClient",
    "OpenAIClient",
    "OllamaClient",
    "LLMRouter",
    "Profile",
    "default_router",
    "default_llm",
]
