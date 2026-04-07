"""Yandex SpeechKit STT/TTS."""

from __future__ import annotations

import aiohttp

from app.core.config import Config
from app.core.logging import get_logger

logger = get_logger(__name__)


class VoiceService:
    """Распознавание и синтез речи через Yandex SpeechKit."""

    stt_url = "https://stt.api.cloud.yandex.net/speech/v1/stt:recognize"
    tts_url = "https://tts.api.cloud.yandex.net/speech/v1/tts:synthesize"

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or Config.YANDEX_API_KEY

    async def speech_to_text(self, audio_bytes: bytes) -> str | None:
        if not self.api_key:
            return None
        headers = {"Authorization": f"Api-Key {self.api_key}"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.stt_url, headers=headers, data=audio_bytes, timeout=10
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("result", "")
                    logger.error("Yandex STT %s", resp.status)
        except Exception as exc:  # pragma: no cover
            logger.exception("STT error: %s", exc)
        return None

    async def text_to_speech(self, text: str, voice: str = "jane") -> bytes | None:
        if not self.api_key:
            return None
        headers = {"Authorization": f"Api-Key {self.api_key}"}
        data = {
            "text": text[:500],
            "voice": voice,
            "emotion": "neutral",
            "speed": "1.0",
            "format": "oggopus",
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.tts_url, headers=headers, data=data, timeout=10
                ) as resp:
                    if resp.status == 200:
                        return await resp.read()
                    logger.error("Yandex TTS %s", resp.status)
        except Exception as exc:  # pragma: no cover
            logger.exception("TTS error: %s", exc)
        return None
