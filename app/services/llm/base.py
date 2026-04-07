"""Базовые типы LLM-слоя: протокол клиента, сообщения, исключения."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable

Role = Literal["system", "user", "assistant", "tool"]


@dataclass(slots=True)
class ChatMessage:
    role: Role
    content: str
    name: str | None = None
    tool_call_id: str | None = None

    def to_openai(self) -> dict[str, Any]:
        d: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.name:
            d["name"] = self.name
        if self.tool_call_id:
            d["tool_call_id"] = self.tool_call_id
        return d


@dataclass(slots=True)
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass(slots=True)
class ChatResponse:
    text: str
    model: str
    usage: Usage = field(default_factory=Usage)
    raw: dict[str, Any] | None = None


class LLMError(Exception):
    """Сбой работы LLM-провайдера."""


@runtime_checkable
class LLMClient(Protocol):
    """Минимальный протокол LLM-клиента (chat + stream)."""

    name: str
    model: str

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> ChatResponse: ...

    def stream(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> AsyncIterator[str]: ...
