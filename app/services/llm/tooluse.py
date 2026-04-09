"""Anthropic native tool use в chat-flow.

Sprint 4: позволяет Claude **реально вызывать** наши tools (web_search, now,
calculator, fetch_url) во время обычного чата — а не только в orchestrator
pipeline.

Цикл:
1. Отправляем сообщение + список tools
2. Claude может вернуть `tool_use` блок вместо текста
3. Мы выполняем tool, кладём результат в `tool_result`
4. Цикл повторяется до финального текста (max 4 итерации)

Работает только с Anthropic API. Если ANTHROPIC_API_KEY не задан — модуль
gracefully no-op возвращает None, чат идёт обычным путём.
"""

from __future__ import annotations

import json
from typing import Any

import aiohttp

from app.core.config import Config
from app.core.logging import get_logger
from app.services.tools import ToolRegistry, default_registry

logger = get_logger(__name__)

API_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-sonnet-4-6"
MAX_ITERATIONS = 4


class ToolUseChat:
    """Anthropic Messages API с native tool use loop."""

    def __init__(self, registry: ToolRegistry | None = None) -> None:
        self.registry = registry or default_registry()

    def is_available(self) -> bool:
        return bool(Config.ANTHROPIC_API_KEY)

    async def chat(
        self,
        system: str,
        messages: list[dict[str, Any]],
        *,
        max_tokens: int = 1500,
        temperature: float = 0.7,
        user_id: str = "",
    ) -> str | None:
        """Возвращает финальный текстовый ответ.

        messages — список dict-ов в формате Anthropic ({role, content}).
        """
        if not self.is_available():
            return None

        headers = {
            "x-api-key": Config.ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        tools = self.registry.to_anthropic()
        msgs = [dict(m) for m in messages]

        for _ in range(MAX_ITERATIONS):
            payload = {
                "model": MODEL,
                "system": system,
                "messages": msgs,
                "tools": tools,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        API_URL, headers=headers, json=payload, timeout=60
                    ) as resp:
                        if resp.status != 200:
                            body = await resp.text()
                            logger.warning("anthropic tool-use %s: %s", resp.status, body[:300])
                            return None
                        data = await resp.json()
            except Exception as exc:
                logger.warning("anthropic tool-use call failed: %s", exc)
                return None

            content_blocks = data.get("content", [])
            stop_reason = data.get("stop_reason")

            # Если модель вернула финальный текст — возвращаем
            if stop_reason != "tool_use":
                texts = [b.get("text", "") for b in content_blocks if b.get("type") == "text"]
                return "".join(texts).strip() or None

            # Иначе — есть tool_use блоки. Добавляем ассистент-реплику в историю
            msgs.append({"role": "assistant", "content": content_blocks})

            # Вызываем все tools и собираем результаты
            tool_results: list[dict[str, Any]] = []
            for block in content_blocks:
                if block.get("type") != "tool_use":
                    continue
                tool_name = block.get("name", "")
                tool_input = block.get("input", {})
                tool_use_id = block.get("id", "")
                try:
                    # Инжектим _user_id для tools которые его принимают
                    import inspect as _inspect
                    _tool_func = self.registry.get(tool_name).func
                    _sig = _inspect.signature(_tool_func)
                    if "_user_id" in _sig.parameters and user_id:
                        tool_input["_user_id"] = user_id
                    logger.info("tool call: %s, user_id=%s", tool_name, user_id[:8] if user_id else "none")
                    result = await self.registry.call(tool_name, **tool_input)
                    result_str = str(result)
                except Exception as exc:
                    result_str = f"error: {exc}"
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": result_str[:4000],
                    }
                )

            msgs.append({"role": "user", "content": tool_results})

        # Превышен max_iterations
        return None
