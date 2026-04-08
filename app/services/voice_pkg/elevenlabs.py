"""ElevenLabs streaming TTS клиент.

Премиум TTS с естественными паузами, дыханием, эмоциями.
Использует Eleven multilingual v2 + Turbo v2.5.

Endpoint: https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import aiohttp

from app.core.config import Config
from app.core.logging import get_logger

logger = get_logger(__name__)

API_BASE = "https://api.elevenlabs.io/v1"
DEFAULT_VOICE = "EXAVITQu4vr4xnSDxMaL"  # Bella — нейтральный женский, multilingual

# Глобальный множитель скорости речи (+10%). ElevenLabs принимает speed
# в [0.7; 1.2] (поле в voice_settings model v3+).
SPEED_BOOST = 1.10


class ElevenLabsTTS:
    """Streaming TTS поверх ElevenLabs API."""

    def __init__(
        self,
        api_key: str | None = None,
        voice_id: str | None = None,
        model: str | None = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else Config.ELEVENLABS_API_KEY
        self.voice_id = voice_id or Config.ELEVENLABS_VOICE_ID or DEFAULT_VOICE
        self.model = model or Config.ELEVENLABS_MODEL or "eleven_multilingual_v2"

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def _voice_settings(self, tone: str = "warm") -> dict[str, float | bool]:
        """Маппинг наших tone'ов на ElevenLabs voice_settings."""
        presets: dict[str, dict[str, float]] = {
            "warm": {"stability": 0.65, "similarity_boost": 0.85, "style": 0.35},
            "calm": {"stability": 0.85, "similarity_boost": 0.85, "style": 0.15},
            "energetic": {"stability": 0.35, "similarity_boost": 0.75, "style": 0.75},
            "supportive": {"stability": 0.75, "similarity_boost": 0.85, "style": 0.45},
            "playful": {"stability": 0.40, "similarity_boost": 0.70, "style": 0.80},
            "clarifying": {"stability": 0.80, "similarity_boost": 0.85, "style": 0.20},
        }
        s = presets.get(tone, presets["warm"])
        # speed clamping в допустимом ElevenLabs диапазоне [0.7; 1.2]
        speed = round(min(1.2, max(0.7, 1.0 * SPEED_BOOST)), 3)
        return {
            "stability": s["stability"],
            "similarity_boost": s["similarity_boost"],
            "style": s["style"],
            "use_speaker_boost": True,
            "speed": speed,
        }

    async def synthesize(
        self,
        text: str,
        *,
        tone: str = "warm",
        output_format: str = "mp3_44100_128",
    ) -> bytes | None:
        """Синхронный (не stream) синтез — возвращает целый mp3-файл."""
        if not self.is_configured() or not text:
            return None
        url = f"{API_BASE}/text-to-speech/{self.voice_id}"
        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }
        payload = {
            "text": text,
            "model_id": self.model,
            "voice_settings": self._voice_settings(tone),
            "output_format": output_format,
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload, timeout=60) as resp:
                    if resp.status != 200:
                        body = await resp.text()
                        logger.error("ElevenLabs %s: %s", resp.status, body[:300])
                        return None
                    return await resp.read()
        except Exception as exc:  # pragma: no cover
            logger.exception("ElevenLabs error: %s", exc)
            return None

    async def stream(
        self,
        text: str,
        *,
        tone: str = "warm",
    ) -> AsyncIterator[bytes]:
        """Streaming TTS — отдаёт MP3 chunks по мере генерации."""
        if not self.is_configured() or not text:
            return
        url = f"{API_BASE}/text-to-speech/{self.voice_id}/stream"
        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }
        payload = {
            "text": text,
            "model_id": self.model,
            "voice_settings": self._voice_settings(tone),
            "optimize_streaming_latency": 3,
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload, timeout=60) as resp:
                    if resp.status != 200:
                        body = await resp.text()
                        logger.error("ElevenLabs stream %s: %s", resp.status, body[:300])
                        return
                    async for chunk in resp.content.iter_chunked(4096):
                        if chunk:
                            yield chunk
        except Exception as exc:  # pragma: no cover
            logger.exception("ElevenLabs stream error: %s", exc)

    async def list_voices(self) -> list[dict] | None:
        if not self.is_configured():
            return None
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{API_BASE}/voices",
                    headers={"xi-api-key": self.api_key},
                    timeout=15,
                ) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()
                    return data.get("voices", [])
        except Exception:  # pragma: no cover
            return None
