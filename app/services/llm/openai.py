"""OpenAI-адаптер (использует ту же OpenAI-совместимую базу)."""

from __future__ import annotations

from app.core.config import Config

from .openai_compat import OpenAICompatibleClient


class OpenAIClient(OpenAICompatibleClient):
    name = "openai"

    def __init__(self, api_key: str | None = None, model: str = "gpt-4o-mini") -> None:
        super().__init__(
            api_key=api_key if api_key is not None else Config.OPENAI_API_KEY,
            base_url="https://api.openai.com/v1",
            model=model,
        )
