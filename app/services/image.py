"""Replicate FLUX image generation.

Sprint 2: Text → image через Replicate (FLUX.1 Schnell — самая быстрая модель,
1-2 секунды на картинку, ~$0.003).

Дешёвая альтернатива DALL-E 3 ($0.04-0.08/img).
"""

from __future__ import annotations

import asyncio
from typing import Any

import aiohttp

from app.core.config import Config
from app.core.logging import get_logger

logger = get_logger(__name__)

API_BASE = "https://api.replicate.com/v1"


class ReplicateImageGen:
    """Async обёртка вокруг Replicate predictions API."""

    def __init__(
        self,
        api_token: str | None = None,
        model: str | None = None,
    ) -> None:
        self.api_token = api_token if api_token is not None else Config.REPLICATE_API_TOKEN
        self.model = model or Config.REPLICATE_MODEL or "black-forest-labs/flux-schnell"

    def is_configured(self) -> bool:
        return bool(self.api_token)

    async def generate(
        self,
        prompt: str,
        *,
        aspect_ratio: str = "1:1",
        num_outputs: int = 1,
        seed: int | None = None,
    ) -> list[str] | None:
        """Возвращает список URL'ов сгенерированных картинок."""
        if not self.is_configured() or not prompt:
            return None

        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
            "Prefer": "wait",  # синхронный режим — ждём результат до 60 сек
        }
        payload: dict[str, Any] = {
            "input": {
                "prompt": prompt,
                "aspect_ratio": aspect_ratio,
                "num_outputs": num_outputs,
                "output_format": "webp",
                "output_quality": 90,
            }
        }
        if seed is not None:
            payload["input"]["seed"] = seed

        url = f"{API_BASE}/models/{self.model}/predictions"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, headers=headers, json=payload, timeout=90
                ) as resp:
                    if resp.status not in (200, 201):
                        body = await resp.text()
                        logger.error("Replicate %s: %s", resp.status, body[:300])
                        return None
                    data = await resp.json()

                # Если status сразу `succeeded` — output уже здесь
                if data.get("status") == "succeeded":
                    return self._extract_urls(data.get("output"))

                # Иначе polling
                pred_id = data.get("id")
                if not pred_id:
                    return None

                for _ in range(60):
                    await asyncio.sleep(1)
                    async with session.get(
                        f"{API_BASE}/predictions/{pred_id}",
                        headers=headers,
                        timeout=10,
                    ) as poll:
                        if poll.status != 200:
                            continue
                        info = await poll.json()
                        status = info.get("status")
                        if status == "succeeded":
                            return self._extract_urls(info.get("output"))
                        if status == "failed":
                            logger.error("Replicate failed: %s", info.get("error"))
                            return None
                logger.warning("Replicate timeout")
                return None
        except Exception as exc:  # pragma: no cover
            logger.exception("Replicate error: %s", exc)
            return None

    @staticmethod
    def _extract_urls(output: Any) -> list[str]:
        if isinstance(output, list):
            return [str(u) for u in output if u]
        if isinstance(output, str):
            return [output]
        return []
