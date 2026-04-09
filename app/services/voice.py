"""Voice services: STT (Deepgram + Yandex) + TTS (Fish Audio + ElevenLabs + Yandex).

TTS fallback chain: Fish Audio (Jarvis) → ElevenLabs → Yandex madirus.
Fish Audio — основной TTS, голос Джарвиса из Iron Man.
Web: mp3 формат (для <audio> элемента). Telegram: opus (для sendVoice).
Скорость speech +21% для Yandex fallback (1.10 × 1.10, см. SPEED_BOOST).
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

# === Каталог голосов Yandex SpeechKit (fallback) ===
YANDEX_VOICES = {
    "madirus": {
        "label": "Madirus (сербский баритон, ~Бикович)",
        "gender": "male",
        "accent": "serbian",
        "default": False,
    },
    "jarvis": {
        "label": "Джарвис (рус. дубляж, ~Колган)",
        "gender": "male",
        "accent": "russian",
        "yandex_voice": "filipp",
    },
    "filipp": {"label": "Филипп (спокойный)", "gender": "male"},
    "ermil": {"label": "Ермил (выразительный)", "gender": "male"},
    "zahar": {"label": "Захар (энергичный)", "gender": "male"},
    "kuznetsov": {"label": "Кузнецов (нейтральный)", "gender": "male"},
    "jane": {"label": "Джейн (нейтральный)", "gender": "female"},
    "oksana": {"label": "Оксана (тёплый)", "gender": "female"},
    "alyss": {"label": "Алисса (молодой)", "gender": "female"},
    "omazh": {"label": "Омаж (мягкий)", "gender": "female"},
}

JARVIS_SETTINGS = {
    "yandex_voice": "filipp",
    "emotion": "neutral",
    "speed_multiplier": 0.95,
}

SPEED_BOOST = 1.21

_TONE_BASE = {
    "warm": ("good", 1.0),
    "calm": ("neutral", 0.95),
    "energetic": ("good", 1.1),
    "supportive": ("good", 0.93),
    "playful": ("good", 1.05),
    "clarifying": ("neutral", 0.97),
}

TONE_TO_YANDEX = {
    name: (emotion, round(min(3.0, max(0.1, base_speed * SPEED_BOOST)), 3))
    for name, (emotion, base_speed) in _TONE_BASE.items()
}


def text_to_ssml(text: str) -> str:
    if not text:
        return text
    safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    safe = re.sub(r"\.{3,}|…", '<break time="500ms"/>', safe)
    safe = re.sub(r"\n\s*\n", '<break time="700ms"/>', safe)
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
        if not self.api_key:
            return None
        emotion, speed = TONE_TO_YANDEX.get(
            tone, ("neutral", round(1.0 * SPEED_BOOST, 3))
        )
        actual_voice = voice
        if voice == "jarvis":
            actual_voice = JARVIS_SETTINGS["yandex_voice"]
            emotion = JARVIS_SETTINGS["emotion"]
            speed = round(speed * JARVIS_SETTINGS["speed_multiplier"], 3)
        elif voice == "madirus":
            emotion = "neutral"
        headers = {"Authorization": f"Api-Key {self.api_key}"}
        data: dict[str, str] = {
            "voice": actual_voice,
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
                    if use_ssml and resp.status in (400, 500):
                        return await self.synthesize(
                            text, voice=voice, tone=tone, use_ssml=False
                        )
        except Exception as exc:  # pragma: no cover
            logger.exception("Yandex TTS error: %s", exc)
        return None


class VoiceService:
    """Унифицированный фасад: STT + TTS + voice emotion.

    TTS fallback chain: Fish Audio → ElevenLabs → Yandex.
    Fish Audio — основной TTS (голос Джарвиса из Iron Man).
    Web: mp3 (браузерный <audio> не поддерживает opus).
    Telegram: opus (через synthesize_opus напрямую).

    Если Fish Audio вернёт ошибку (402 баланс, 5xx) — автоматически
    переключается на Yandex (без перезапуска).
    """

    def __init__(
        self,
        deepgram: DeepgramSTT | None = None,
        yandex: YandexSpeechKit | None = None,
    ) -> None:
        self.deepgram = deepgram or DeepgramSTT()
        self.yandex = yandex or YandexSpeechKit()
        self._eleven = None
        self._fish = None
        self._hume = None

    def _get_eleven(self):
        if self._eleven is None:
            from app.services.voice_pkg.elevenlabs import ElevenLabsTTS
            self._eleven = ElevenLabsTTS()
        return self._eleven

    def _get_fish(self):
        if self._fish is None:
            from app.services.voice_pkg.fish_audio import FishAudioTTS
            self._fish = FishAudioTTS()
        return self._fish

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
        prefer: str = "auto",  # auto | fish | elevenlabs | yandex
    ) -> tuple[bytes | None, str]:
        # Fish Audio — приоритетный TTS (голос Джарвиса)
        # mp3 для веб-плеера (opus не поддерживается браузерным <audio>)
        if prefer in ("auto", "fish"):
            fish = self._get_fish()
            if fish.is_configured():
                audio = await fish.synthesize(text, tone=tone, format="mp3")
                if audio:
                    return audio, "fish_audio"

        # ElevenLabs — premium fallback
        if prefer in ("auto", "elevenlabs") and Config.ELEVENLABS_API_KEY:
            audio = await self._get_eleven().synthesize(text, tone=tone)
            if audio:
                return audio, "elevenlabs"

        # Yandex — базовый fallback
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
        # Fish Audio — приоритетный стрим (mp3 для веб-плеера)
        # Важно: если Fish Audio вернёт 0 чанков (402/ошибка),
        # НЕ делаем return — падаем на fallback.
        fish = self._get_fish()
        if fish.is_configured():
            yielded = False
            async for chunk in fish.stream(text, tone=tone, format="mp3"):
                yielded = True
                yield chunk
            if yielded:
                return
            logger.warning("Fish Audio stream returned 0 chunks, trying fallback")

        # ElevenLabs stream (fallback #1)
        if Config.ELEVENLABS_API_KEY:
            yielded = False
            async for chunk in self._get_eleven().stream(text, tone=tone):
                yielded = True
                yield chunk
            if yielded:
                return

        # Yandex — не стримит, отдаём целиком (fallback #2)
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
        voices = dict(YANDEX_VOICES)
        fish = self._get_fish()
        if fish.is_configured():
            voices["jarvis"] = {
                "label": "Джарвис (Fish Audio — Iron Man style)",
                "gender": "male",
                "accent": "english",
                "default": True,
                "provider": "fish_audio",
            }
        return voices

    # Backward-compat
    async def speech_to_text(self, audio_bytes: bytes, format: str = "ogg") -> str | None:  # noqa: ARG002
        text, _ = await self.transcribe(audio_bytes)
        return text

    async def text_to_speech(self, text: str, voice: str = "madirus") -> bytes | None:
        audio, _ = await self.synthesize(text, voice=voice)
        return audio
