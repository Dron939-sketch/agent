"""Voice services: STT (Deepgram + Yandex), TTS (Yandex).

`VoiceService.transcribe()` авто-выбирает провайдера: Deepgram, если задан
`DEEPGRAM_API_KEY`, иначе Yandex SpeechKit. TTS — только Yandex (для русского).
"""

from __future__ import annotations

import aiohttp

from app.core.config import Config
from app.core.logging import get_logger

logger = get_logger(__name__)

DEEPGRAM_URL = "https://api.deepgram.com/v1/listen"
YANDEX_STT_URL = "https://stt.api.cloud.yandex.net/speech/v1/stt:recognize"
YANDEX_TTS_URL = "https://tts.api.cloud.yandex.net/speech/v1/tts:synthesize"


class DeepgramSTT:
    """Минимальный async-клиент Deepgram listen API."""

    def __init__(self, api_key: str | None = None, model: str = "nova-2") -> None:
        self.api_key = api_key if api_key is not None else Config.DEEPGRAM_API_KEY
        self.model = model

    async def transcribe(
        self,
        audio_bytes: bytes,
        *,
        content_type: str = "audio/webm",
        language: str = "ru",
    ) -> str | None:
        if not self.api_key:
            return None
        params = {"model": self.model, "language": language, "smart_format": "true"}
        headers = {
            "Authorization": f"Token {self.api_key}",
            "Content-Type": content_type,
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    DEEPGRAM_URL,
                    headers=headers,
                    params=params,
                    data=audio_bytes,
                    timeout=30,
                ) as resp:
                    if resp.status != 200:
                        body = await resp.text()
                        logger.error("Deepgram %s: %s", resp.status, body[:300])
                        return None
                    data = await resp.json()
                    return (
                        data.get("results", {})
                        .get("channels", [{}])[0]
                        .get("alternatives", [{}])[0]
                        .get("transcript", "")
                        or None
                    )
        except Exception as exc:  # pragma: no cover
            logger.exception("Deepgram error: %s", exc)
            return None


class YandexSpeechKit:
    """Yandex SpeechKit STT + TTS."""

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key if api_key is not None else Config.YANDEX_API_KEY

    async def transcribe(self, audio_bytes: bytes) -> str | None:
        if not self.api_key:
            return None
        headers = {"Authorization": f"Api-Key {self.api_key}"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    YANDEX_STT_URL, headers=headers, data=audio_bytes, timeout=10
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("result") or None
                    logger.error("Yandex STT %s", resp.status)
        except Exception as exc:  # pragma: no cover
            logger.exception("Yandex STT error: %s", exc)
        return None

    async def synthesize(self, text: str, voice: str = "jane") -> bytes | None:
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
                    YANDEX_TTS_URL, headers=headers, data=data, timeout=10
                ) as resp:
                    if resp.status == 200:
                        return await resp.read()
                    logger.error("Yandex TTS %s", resp.status)
        except Exception as exc:  # pragma: no cover
            logger.exception("Yandex TTS error: %s", exc)
        return None


class VoiceService:
    """Унифицированный фасад: транскрипция через Deepgram→Yandex, TTS через Yandex."""

    def __init__(
        self,
        deepgram: DeepgramSTT | None = None,
        yandex: YandexSpeechKit | None = None,
    ) -> None:
        self.deepgram = deepgram or DeepgramSTT()
        self.yandex = yandex or YandexSpeechKit()

    async def transcribe(
        self,
        audio_bytes: bytes,
        *,
        content_type: str = "audio/webm",
        language: str = "ru",
    ) -> tuple[str | None, str]:
        """Возвращает (текст, использованный_провайдер)."""
        if Config.DEEPGRAM_API_KEY:
            text = await self.deepgram.transcribe(
                audio_bytes, content_type=content_type, language=language
            )
            if text:
                return text, "deepgram"
        if Config.YANDEX_API_KEY:
            text = await self.yandex.transcribe(audio_bytes)
            if text:
                return text, "yandex"
        return None, "none"

    async def synthesize(self, text: str, voice: str = "jane") -> bytes | None:
        return await self.yandex.synthesize(text, voice=voice)

    # Backward-compat (старое имя из Фазы 1)
    async def speech_to_text(self, audio_bytes: bytes, format: str = "ogg") -> str | None:  # noqa: ARG002
        text, _ = await self.transcribe(audio_bytes)
        return text

    async def text_to_speech(self, text: str, voice: str = "jane") -> bytes | None:
        return await self.synthesize(text, voice=voice)
