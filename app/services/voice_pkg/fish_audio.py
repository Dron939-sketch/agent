"""Fish Audio TTS — облачный провайдер с клоном голоса Джарвиса.

Быстрый (<500ms), качественный (90%+), готовый голос Джарвиса из каталога.
Поддержка эмоций: [whisper], [excited], [calm], [angry] и 50+ тегов.

Env:
  FISH_AUDIO_API_KEY=...          (получить: https://fish.audio/)
  FISH_AUDIO_JARVIS_VOICE_ID=612b878b113047d9a770c069c8b4fdfe  (default)

Тарифы:
  Free: 7 мин/мес, 500 символов/запрос
  Plus: $5.50/мес, 200 мин, 15000 символов, API
  Pay-as-you-go: $15/1M bytes (~12ч речи)
"""

from __future__ import annotations

import io
import os
from collections.abc import AsyncIterator

import aiohttp

from app.core.logging import get_logger

logger = get_logger(__name__)

FISH_API_URL = "https://api.fish.audio/v1/tts"
FISH_API_KEY = os.environ.get("FISH_AUDIO_API_KEY", "")

# Готовый клон Джарвиса из каталога Fish Audio (48K+ пользователей)
JARVIS_VOICE_ID = os.environ.get(
    "FISH_AUDIO_JARVIS_VOICE_ID",
    "612b878b113047d9a770c069c8b4fdfe",
)

# Маппинг наших tone → Fish Audio emotion tags
TONE_TO_EMOTION: dict[str, str] = {
    "warm": "",
    "calm": "[calm]",
    "energetic": "[excited]",
    "supportive": "[gentle]",
    "playful": "[happy]",
    "clarifying": "",
    "jarvis": "[calm]",  # Джарвис всегда спокоен
}


class FishAudioTTS:
    """Fish Audio TTS провайдер с поддержкой клонированных голосов."""

    def __init__(
        self,
        api_key: str | None = None,
        voice_id: str | None = None,
    ) -> None:
        self.api_key = api_key or FISH_API_KEY
        self.voice_id = voice_id or JARVIS_VOICE_ID

    def is_configured(self) -> bool:
        return bool(self.api_key)

    async def synthesize(
        self,
        text: str,
        *,
        voice_id: str | None = None,
        tone: str = "warm",
        format: str = "mp3",
    ) -> bytes | None:
        """Генерирует аудио через Fish Audio API.

        Returns: audio bytes (mp3/wav/ogg) или None при ошибке.
        """
        if not self.is_configured():
            return None

        vid = voice_id or self.voice_id

        # Добавляем emotion tag если есть
        emotion_tag = TONE_TO_EMOTION.get(tone, "")
        processed_text = f"{emotion_tag} {text}".strip() if emotion_tag else text

        payload = {
            "text": processed_text[:2000],
            "reference_id": vid,
            "format": format,
            "streaming": False,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    FISH_API_URL,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status != 200:
                        body = await resp.text()
                        logger.error("Fish Audio TTS %s: %s", resp.status, body[:300])
                        return None
                    audio = await resp.read()
                    logger.info(
                        "Fish Audio: synthesized %d chars, %d bytes (%s)",
                        len(text), len(audio), format,
                    )
                    return audio
        except Exception as exc:
            logger.error("Fish Audio TTS error: %s", exc)
            return None

    async def synthesize_stream(
        self,
        text: str,
        *,
        voice_id: str | None = None,
        tone: str = "warm",
        chunk_size: int = 4096,
    ) -> AsyncIterator[bytes]:
        """Streaming TTS — отдаёт audio chunks по мере генерации."""
        if not self.is_configured():
            return

        vid = voice_id or self.voice_id
        emotion_tag = TONE_TO_EMOTION.get(tone, "")
        processed_text = f"{emotion_tag} {text}".strip() if emotion_tag else text

        payload = {
            "text": processed_text[:2000],
            "reference_id": vid,
            "format": "mp3",
            "streaming": True,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    FISH_API_URL,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=60),
                ) as resp:
                    if resp.status != 200:
                        body = await resp.text()
                        logger.error("Fish Audio stream %s: %s", resp.status, body[:300])
                        return
                    async for chunk in resp.content.iter_chunked(chunk_size):
                        yield chunk
        except Exception as exc:
            logger.error("Fish Audio stream error: %s", exc)

    async def clone_voice(
        self,
        audio_bytes: bytes,
        title: str = "Custom Voice",
        description: str = "",
    ) -> str | None:
        """Создаёт persistent voice clone из аудио-сэмпла.

        Returns: voice_id для последующего использования.
        Требует 10-15 секунд чистого аудио.
        """
        if not self.is_configured():
            return None

        headers = {
            "Authorization": f"Bearer {self.api_key}",
        }

        form = aiohttp.FormData()
        form.add_field("title", title)
        form.add_field("description", description or f"Voice clone: {title}")
        form.add_field(
            "voices",
            audio_bytes,
            filename="sample.wav",
            content_type="audio/wav",
        )

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.fish.audio/v1/voices",
                    data=form,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=60),
                ) as resp:
                    if resp.status not in (200, 201):
                        body = await resp.text()
                        logger.error("Fish Audio clone %s: %s", resp.status, body[:300])
                        return None
                    data = await resp.json()
                    voice_id = data.get("id", "")
                    logger.info("Fish Audio: voice cloned → %s", voice_id)
                    return voice_id
        except Exception as exc:
            logger.error("Fish Audio clone error: %s", exc)
            return None


# === Singleton ===

_instance: FishAudioTTS | None = None


def get_fish_audio() -> FishAudioTTS:
    global _instance
    if _instance is None:
        _instance = FishAudioTTS()
    return _instance
