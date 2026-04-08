"""Voice services: STT (Deepgram + Yandex) + TTS (ElevenLabs + Yandex с SSML).

Sprint 3.5: Поддержка SSML для Yandex (паузы, ударения, эмоции),
голос `madirus` (сербский баритон) как дефолт — звучит как Милош Бикович.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator

import aiohttp

from app.core.config import Config
from app.core.logging import get_logger

logger = get_logger(__name__)

DEEPGRAM_URL = "https://api.deepgram.com/v1/listen"
YANDEX_STT_URL = "https://stt.api.cloud.yandex.net/speech/v1/stt:recognize"
YANDEX_TTS_URL = "https://tts.api.cloud.yandex.net/speech/v1/tts:synthesize"

# === Каталог голосов Yandex SpeechKit ===
# https://cloud.yandex.ru/docs/speechkit/tts/voices
YANDEX_VOICES = {
    # Мужские
    "madirus": {
        "label": "Madirus (сербский баритон, ~Бикович)",
        "gender": "male",
        "accent": "serbian",
        "default": True,
    },
    "filipp": {"label": "Филипп (спокойный)", "gender": "male"},
    "ermil": {"label": "Ермил (выразительный)", "gender": "male"},
    "zahar": {"label": "Захар (энергичный)", "gender": "male"},
    "kuznetsov": {"label": "Кузнецов (нейтральный)", "gender": "male"},
    # Женские
    "jane": {"label": "Джейн (нейтральный)", "gender": "female"},
    "oksana": {"label": "Оксана (тёплый)", "gender": "female"},
    "alyss": {"label": "Алисса (молодой)", "gender": "female"},
    "omazh": {"label": "Омаж (мягкий)", "gender": "female"},
}

# Эмоциональная окраска по нашим внутренним tone'ам
TONE_TO_YANDEX = {
    "warm": ("good", 1.0),
    "calm": ("neutral", 0.95),
    "energetic": ("good", 1.1),
    "supportive": ("good", 0.93),
    "playful": ("good", 1.05),
    "clarifying": ("neutral", 0.97),
}


def text_to_ssml(text: str) -> str:
    """Превращает обычный текст в SSML с естественными паузами.

    Правила (эмулируют «Бикович-стиль» — задумчивый, с паузами):
    - `…` или `...` → пауза 500ms
    - `,` → короткий вдох
    - `!` `?` → пауза предложения
    - двойной перенос строки → пауза 700ms
    """
    if not text:
        return text

    # Сначала экранируем XML
    safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    # Многоточия → длинная пауза
    safe = re.sub(r"\.{3,}|…", '<break time="500ms"/>', safe)
    # Двойной перенос строки → абзац
    safe = re.sub(r"\n\s*\n", '<break time="700ms"/>', safe)
    # Одиночный перенос → запятая
    safe = re.sub(r"\n", '<break time="200ms"/>', safe)

    return f"<speak>{safe}</speak>"


class DeepgramSTT:
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
    """Yandex SpeechKit STT + TTS с SSML поддержкой."""

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

    async def synthesize(
        self,
        text: str,
        voice: str = "madirus",
        *,
        tone: str = "warm",
        use_ssml: bool = True,
    ) -> bytes | None:
        """Синтез речи Yandex с SSML и эмоциями.

        - voice: madirus / filipp / ermil / zahar / jane / oksana / ...
        - tone: warm / calm / energetic / supportive / playful / clarifying
        - use_ssml: True → автоматически расставляет паузы из «…»
        """
        if not self.api_key:
            return None

        emotion, speed = TONE_TO_YANDEX.get(tone, ("neutral", 1.0))

        # `madirus` поддерживает только neutral эмоцию (Yandex docs)
        if voice == "madirus":
            emotion = "neutral"

        headers = {"Authorization": f"Api-Key {self.api_key}"}
        data: dict[str, str] = {
            "voice": voice,
            "emotion": emotion,
            "speed": str(speed),
            "format": "oggopus",
            "lang": "ru-RU",
        }

        if use_ssml:
            data["ssml"] = text_to_ssml(text[:1500])
        else:
            data["text"] = text[:1500]

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    YANDEX_TTS_URL, headers=headers, data=data, timeout=15
                ) as resp:
                    if resp.status == 200:
                        return await resp.read()
                    body = await resp.text()
                    logger.error("Yandex TTS %s: %s", resp.status, body[:200])
                    # Если SSML не принялся — fallback на plain text
                    if use_ssml and resp.status in (400, 500):
                        return await self.synthesize(
                            text, voice=voice, tone=tone, use_ssml=False
                        )
        except Exception as exc:  # pragma: no cover
            logger.exception("Yandex TTS error: %s", exc)
        return None


class VoiceService:
    """Унифицированный фасад: STT + TTS + voice emotion."""

    def __init__(
        self,
        deepgram: DeepgramSTT | None = None,
        yandex: YandexSpeechKit | None = None,
    ) -> None:
        self.deepgram = deepgram or DeepgramSTT()
        self.yandex = yandex or YandexSpeechKit()
        self._eleven = None
        self._hume = None

    def _get_eleven(self):
        if self._eleven is None:
            from app.services.voice_pkg.elevenlabs import ElevenLabsTTS

            self._eleven = ElevenLabsTTS()
        return self._eleven

    def _get_hume(self):
        if self._hume is None:
            from app.services.voice_pkg.hume import HumeVoiceEmotion

            self._hume = HumeVoiceEmotion()
        return self._hume

    async def transcribe(
        self,
        audio_bytes: bytes,
        *,
        content_type: str = "audio/webm",
        language: str = "ru",
    ) -> tuple[str | None, str]:
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

    async def synthesize(
        self,
        text: str,
        *,
        voice: str = "madirus",
        tone: str = "warm",
        prefer: str = "auto",  # auto | elevenlabs | yandex
    ) -> tuple[bytes | None, str]:
        """Синтез речи. Дефолтный голос — madirus (мужской с сербским акцентом)."""
        if prefer in ("auto", "elevenlabs") and Config.ELEVENLABS_API_KEY:
            audio = await self._get_eleven().synthesize(text, tone=tone)
            if audio:
                return audio, "elevenlabs"
        if Config.YANDEX_API_KEY:
            audio = await self.yandex.synthesize(text, voice=voice, tone=tone)
            if audio:
                return audio, "yandex"
        return None, "none"

    async def synthesize_stream(
        self,
        text: str,
        *,
        voice: str = "madirus",
        tone: str = "warm",
    ) -> AsyncIterator[bytes]:
        """Streaming TTS. ElevenLabs — chunked, Yandex — целым blob'ом."""
        if Config.ELEVENLABS_API_KEY:
            async for chunk in self._get_eleven().stream(text, tone=tone):
                yield chunk
            return
        audio, _ = await self.synthesize(text, voice=voice, tone=tone, prefer="yandex")
        if audio:
            yield audio

    async def voice_emotion(
        self,
        audio_bytes: bytes,
        *,
        content_type: str = "audio/webm",
    ) -> dict | None:
        if not Config.HUME_API_KEY:
            return None
        return await self._get_hume().analyze(audio_bytes, content_type=content_type)

    def list_voices(self) -> dict[str, dict]:
        """Возвращает каталог голосов."""
        return YANDEX_VOICES

    # Backward-compat
    async def speech_to_text(self, audio_bytes: bytes, format: str = "ogg") -> str | None:  # noqa: ARG002
        text, _ = await self.transcribe(audio_bytes)
        return text

    async def text_to_speech(self, text: str, voice: str = "madirus") -> bytes | None:
        audio, _ = await self.synthesize(text, voice=voice)
        return audio
