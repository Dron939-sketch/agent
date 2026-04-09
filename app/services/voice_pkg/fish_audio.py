"""Fish Audio TTS клиент — голос Джарвиса.

Fish Audio: https://fish.audio — премиум TTS с клонированными голосами.
Используется как **основной** TTS провайдер (замена Yandex SpeechKit).

Env:
  FISH_AUDIO_API_KEY   — API-токен с https://fish.audio/app/api-keys/
  FISH_AUDIO_VOICE_ID  — ID голосовой модели из каталога Fish Audio
                         (найди Jarvis-like на https://fish.audio/discover/)

API:
  POST https://api.fish.audio/v1/tts
  Auth: Authorization: Bearer {key}
  Body: {"text": "...", "reference_id": "...", "format": "opus", ...}
  Response: audio bytes (streaming)
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import aiohttp

from app.core.logging import get_logger

logger = get_logger(__name__)

API_URL = "https://api.fish.audio/v1/tts"

# Default Jarvis-like voice. Пользователь может переопределить через
# FISH_AUDIO_VOICE_ID. Это ID из Fish Audio marketplace.
DEFAULT_VOICE_ID = ""  # Задаётся через env


class FishAudioTTS:
    """Fish Audio TTS с поддержкой streaming и multiple output formats."""

    def __init__(
        self,
        api_key: str | None = None,
        voice_id: str | None = None,
    ) -> None:
        self.api_key = (
            api_key
            or os.environ.get("FISH_AUDIO_API_KEY", "")
        ).strip()
        self.voice_id = (
            voice_id
            or os.environ.get("FISH_AUDIO_VOICE_ID", "")
            or DEFAULT_VOICE_ID
        ).strip()

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _body(
        self,
        text: str,
        *,
        format: str = "opus",
        voice_id: str | None = None,
    ) -> dict:
        body: dict = {
            "text": text[:2000],  # Fish Audio text limit
            "format": format,
            "latency": "balanced",  # "normal" для лучшего качества, "balanced" для скорости
        }
        vid = voice_id or self.voice_id
        if vid:
            body["reference_id"] = vid
        return body

    async def synthesize(
        self,
        text: str,
        *,
        tone: str = "warm",  # для совместимости API, Fish Audio не использует tone
        format: str = "opus",
        voice_id: str | None = None,
    ) -> bytes | None:
        """Синтез речи — возвращает полный аудио-файл."""
        if not self.is_configured() or not text:
            return None

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    API_URL,
                    headers=self._headers(),
                    json=self._body(text, format=format, voice_id=voice_id),
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status != 200:
                        body = await resp.text()
                        logger.error(
                            "Fish Audio TTS %s: %s", resp.status, body[:300]
                        )
                        return None
                    audio = await resp.read()
                    if len(audio) < 100:
                        logger.warning("Fish Audio TTS returned tiny audio (%d bytes)", len(audio))
                        return None
                    logger.info(
                        "🐟 Fish Audio TTS: %d bytes, format=%s", len(audio), format
                    )
                    return audio
        except Exception as exc:
            logger.exception("Fish Audio TTS error: %s", exc)
            return None

    async def synthesize_opus(
        self,
        text: str,
        *,
        voice_id: str | None = None,
    ) -> bytes | None:
        """Opus формат — подходит для Telegram sendVoice."""
        return await self.synthesize(text, format="opus", voice_id=voice_id)

    async def synthesize_mp3(
        self,
        text: str,
        *,
        voice_id: str | None = None,
    ) -> bytes | None:
        """MP3 формат — для web-плеера."""
        return await self.synthesize(text, format="mp3", voice_id=voice_id)

    async def stream(
        self,
        text: str,
        *,
        tone: str = "warm",
        format: str = "opus",
        voice_id: str | None = None,
    ) -> AsyncIterator[bytes]:
        """Streaming TTS — возвращает чанки по мере генерации."""
        if not self.is_configured() or not text:
            return

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    API_URL,
                    headers=self._headers(),
                    json=self._body(text, format=format, voice_id=voice_id),
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status != 200:
                        body = await resp.text()
                        logger.error(
                            "Fish Audio stream %s: %s", resp.status, body[:300]
                        )
                        return
                    async for chunk in resp.content.iter_any():
                        if chunk:
                            yield chunk
        except Exception as exc:
            logger.exception("Fish Audio stream error: %s", exc)
