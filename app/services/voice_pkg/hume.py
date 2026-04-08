"""Hume AI Expression Measurement — анализ эмоций по голосу.

Sprint 2: использует Hume Batch Job API для анализа аудио (синхронно).
Возвращает топ-эмоций из 48-измерительного prosody-классификатора.

Документация: https://dev.hume.ai/docs/expression-measurement-api/overview

Альтернатива: WebSocket Streaming (`wss://api.hume.ai/v0/stream/models`) —
используется для realtime, в Sprint 3 добавим. Пока batch — проще и надёжнее.
"""

from __future__ import annotations

import asyncio
from typing import Any

import aiohttp

from app.core.config import Config
from app.core.logging import get_logger

logger = get_logger(__name__)

API_BASE = "https://api.hume.ai/v0"

# Маппинг 48 Hume-эмоций на наши 24 Plutchik (для совместимости с EmotionService)
HUME_TO_PLUTCHIK: dict[str, str] = {
    "Joy": "joy",
    "Excitement": "ecstasy",
    "Amusement": "joy",
    "Contentment": "serenity",
    "Calmness": "calm",
    "Sadness": "sadness",
    "Disappointment": "sadness",
    "Pain": "grief",
    "Tiredness": "pensiveness",
    "Boredom": "boredom",
    "Anger": "anger",
    "Annoyance": "annoyance",
    "Contempt": "contempt",
    "Disgust": "disgust",
    "Horror": "terror",
    "Fear": "fear",
    "Anxiety": "apprehension",
    "Distress": "fear",
    "Surprise (positive)": "surprise",
    "Surprise (negative)": "amazement",
    "Confusion": "confusion",
    "Awe": "amazement",
    "Realization": "anticipation",
    "Concentration": "vigilance",
    "Interest": "interest",
    "Determination": "anticipation",
    "Love": "love",
    "Romance": "love",
    "Admiration": "admiration",
    "Adoration": "admiration",
    "Aesthetic Appreciation": "admiration",
    "Empathic Pain": "grief",
    "Sympathy": "trust",
    "Triumph": "ecstasy",
    "Pride": "joy",
    "Embarrassment": "remorse",
    "Guilt": "remorse",
    "Shame": "remorse",
    "Relief": "serenity",
    "Satisfaction": "serenity",
    "Nostalgia": "pensiveness",
    "Entrancement": "trust",
    "Ecstasy": "ecstasy",
    "Craving": "anticipation",
    "Desire": "anticipation",
    "Doubt": "apprehension",
    "Disapproval": "contempt",
    "Envy": "contempt",
}


class HumeVoiceEmotion:
    """Async обёртка вокруг Hume Batch API."""

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key if api_key is not None else Config.HUME_API_KEY

    def is_configured(self) -> bool:
        return bool(self.api_key)

    async def analyze(self, audio_bytes: bytes, *, content_type: str = "audio/webm") -> dict[str, Any] | None:
        """Анализирует аудио, возвращает {primary, intensity, scores, raw}.

        Использует Batch Job API: создаёт job → polling до завершения → результат.
        Латентность ~2-5 секунд для коротких аудио.
        """
        if not self.is_configured() or not audio_bytes:
            return None

        headers = {"X-Hume-Api-Key": self.api_key}

        try:
            async with aiohttp.ClientSession() as session:
                # 1. Создать job
                form = aiohttp.FormData()
                form.add_field(
                    "json",
                    '{"models": {"prosody": {}}}',
                    content_type="application/json",
                )
                form.add_field(
                    "file",
                    audio_bytes,
                    filename="audio.webm",
                    content_type=content_type,
                )
                async with session.post(
                    f"{API_BASE}/batch/jobs",
                    headers=headers,
                    data=form,
                    timeout=30,
                ) as resp:
                    if resp.status not in (200, 201):
                        body = await resp.text()
                        logger.error("Hume create job %s: %s", resp.status, body[:300])
                        return None
                    job_data = await resp.json()
                    job_id = job_data.get("job_id")

                if not job_id:
                    return None

                # 2. Poll до COMPLETED
                for _ in range(30):  # max 30 секунд
                    await asyncio.sleep(1)
                    async with session.get(
                        f"{API_BASE}/batch/jobs/{job_id}",
                        headers=headers,
                        timeout=10,
                    ) as resp:
                        if resp.status != 200:
                            continue
                        info = await resp.json()
                        status = info.get("state", {}).get("status")
                        if status == "COMPLETED":
                            break
                        if status == "FAILED":
                            logger.error("Hume job failed: %s", info)
                            return None
                else:
                    logger.warning("Hume job timeout")
                    return None

                # 3. Получить predictions
                async with session.get(
                    f"{API_BASE}/batch/jobs/{job_id}/predictions",
                    headers=headers,
                    timeout=15,
                ) as resp:
                    if resp.status != 200:
                        return None
                    predictions = await resp.json()
        except Exception as exc:  # pragma: no cover
            logger.exception("Hume error: %s", exc)
            return None

        return self._aggregate(predictions)

    def _aggregate(self, predictions: list[dict[str, Any]]) -> dict[str, Any] | None:
        """Усредняет эмоции по всем сегментам аудио."""
        if not predictions:
            return None
        try:
            results = predictions[0]["results"]["predictions"][0]["models"]["prosody"][
                "grouped_predictions"
            ]
        except (KeyError, IndexError, TypeError):
            return None

        # Собираем все scores
        scores: dict[str, list[float]] = {}
        for group in results:
            for pred in group.get("predictions", []):
                for emo in pred.get("emotions", []):
                    name = emo.get("name", "")
                    score = float(emo.get("score", 0))
                    scores.setdefault(name, []).append(score)

        if not scores:
            return None

        # Усредняем
        averaged = {k: sum(v) / len(v) for k, v in scores.items()}
        # Сортируем по убыванию
        sorted_emos = sorted(averaged.items(), key=lambda x: x[1], reverse=True)

        if not sorted_emos:
            return None

        top_name, top_score = sorted_emos[0]
        plutchik = HUME_TO_PLUTCHIK.get(top_name, "neutral")

        return {
            "primary": plutchik,
            "primary_raw": top_name,
            "intensity": min(10, max(1, int(round(top_score * 10)))),
            "confidence": round(top_score, 3),
            "top_5": [
                {"name": HUME_TO_PLUTCHIK.get(n, n), "raw": n, "score": round(s, 3)}
                for n, s in sorted_emos[:5]
            ],
        }
