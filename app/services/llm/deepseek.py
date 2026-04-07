"""DeepSeek-адаптер."""

from __future__ import annotations

from app.core.config import Config

from .openai_compat import OpenAICompatibleClient


class DeepSeekClient(OpenAICompatibleClient):
    name = "deepseek"

    def __init__(self, api_key: str | None = None, model: str = "deepseek-chat") -> None:
        super().__init__(
            api_key=api_key if api_key is not None else Config.DEEPSEEK_API_KEY,
            base_url="https://api.deepseek.com/v1",
            model=model,
        )
