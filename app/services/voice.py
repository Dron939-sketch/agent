"""Voice services: STT (Deepgram + Yandex) + TTS (ElevenLabs + Yandex с SSML).

Голос `madirus` (сербский баритон) — звучит как Милош Бикович.
Скорость speech +10% относительно дефолта Yandex (см. SPEED_BOOST).
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
# Примечание: "jarvis" — пресет с голосом filipp в стиле Джарвиса из рус. дубляжа
# (Алексей Колган): спокойный, размеренный, чуть холодный, без лишних эмоций).
YANDEX_VOICES = {
    "madirus": {
        "label": "Madirus (сербский баритон, ~Бикович)",
        "gender": "male",
        "accent": "serbian",
        "default": True,
    },
    "jarvis": {
        "label": "Джарвис (рус. дубляж, ~Колган)",
        "gender": "male",
        "accent": "russian",
        "yandex_voice": "filipp",  # Mapping: jarvis → filipp с настройками
    },
    "jarvis_fish": {
        "label": "Джарвис Fish Audio (облачный, быстрый)",
        "gender": "male",
        "accent": "british",
        "provider": "fish",  # Fish Audio API
    },
    "jarvis_local": {
        "label": "Джарвис XTTS (локальный клон, GPU)",
        "gender": "male",
        "accent": "british",
        "provider": "xtts",  # Coqui XTTS v2
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

# Специальные настройки для пресета "jarvis"
# Стиль Алексея Колгана: спокойный, чёткий, нейтральная эмоция, чуть замедленная речь.
JARVIS_SETTINGS = {
    "yandex_voice": "filipp",
    "emotion": "neutral",
    "speed_multiplier": 0.95,  # Чуть медленнее — более «AI-ассистентский»
}

# Глобальный множитель скорости речи. 1.10 = +10% (быстрее).
# По просьбе пользователя — увеличиваем темп на 10% во всех tone-пресетах.
SPEED_BOOST = 1.10

# Эмоциональная окраска по нашим внутренним tone'ам (base speed)
_TONE_BASE = {
    "warm": ("good", 1.0),
    "calm": ("neutral", 0.95),
    "energetic": ("good", 1.1),
    "supportive": ("good", 0.93),
    "playful": ("good", 1.05),
    "clarifying": ("neutral", 0.97),
}

# Финальные значения с применённым boost'ом. Yandex принимает speed в [0.1; 3.0].
TONE_TO_YANDEX = {
    name: (emotion, round(min(3.0, max(0.1, base_speed * SPEED_BOOST)), 3))
    for name, (emotion, base_speed) in _TONE_BASE.items()
}


def text_to_ssml(text: str) -> str:
    """Превращает обычный текст в SSML с естественными паузами.

    Правила (эмулируют «Бикович-стиль» — задумчивый, с паузами):
    - `…` или `...` → пауза 500ms
    - двойной перенос строки → пауза 700ms
    - одиночный перенос → 200ms
    """
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

    async def transcribe(self, audio_bytes: bytes, *, content_type: str = "audio/webm") -> str | None:
        if not self.api_key:
            return None

        # Yandex STT принимает OGG/Opus нативно.
        # WebM из браузера часто вызывает 400 — конвертируем если возможно.
        data_to_send = audio_bytes
        params: dict[str, str] = {"lang": "ru-RU"}

        if "webm" in content_type:
            converted = await self._convert_webm_to_ogg(audio_bytes)
            if converted:
                data_to_send = converted
                params["format"] = "oggopus"
            else:
                # Отправляем как есть — может повезёт
                params["format"] = "lpcm"

        headers = {"Authorization": f"Api-Key {self.api_key}"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    YANDEX_STT_URL, headers=headers, params=params,
                    data=data_to_send, timeout=15,
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("result") or None
                    body = await resp.text()
                    logger.error("Yandex STT %s: %s", resp.status, body[:200])
        except Exception as exc:  # pragma: no cover
            logger.exception("Yandex STT error: %s", exc)
        return None

    @staticmethod
    async def _convert_webm_to_ogg(audio_bytes: bytes) -> bytes | None:
        """Конвертирует WebM → OGG/Opus через ffmpeg (если доступен)."""
        import asyncio

        try:
            proc = await asyncio.create_subprocess_exec(
                "ffmpeg", "-i", "pipe:0", "-c:a", "libopus", "-f", "ogg", "pipe:1",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=audio_bytes), timeout=10
            )
            if proc.returncode == 0 and stdout:
                return stdout
            logger.debug("ffmpeg conversion failed: %s", stderr[:200] if stderr else "no output")
        except FileNotFoundError:
            logger.debug("ffmpeg not found — sending WebM as-is to Yandex STT")
        except Exception as exc:
            logger.debug("WebM→OGG conversion error: %s", exc)
        return None

    async def synthesize(
        self,
        text: str,
        voice: str = "madirus",
        *,
        tone: str = "warm",
        use_ssml: bool = True,
    ) -> bytes | None:
        """Синтез речи Yandex с SSML и эмоциями."""
        if not self.api_key:
            return None

        emotion, speed = TONE_TO_YANDEX.get(
            tone, ("neutral", round(1.0 * SPEED_BOOST, 3))
        )

        # Пресет "jarvis": маппим на filipp с нейтральной эмоцией и чуть замедленной речью
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
        self._xtts = None
        self._fish = None

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

    def _get_xtts(self):
        if self._xtts is None:
            from app.services.voice_pkg.xtts import get_xtts

            self._xtts = get_xtts()
        return self._xtts

    def _get_fish(self):
        if self._fish is None:
            from app.services.voice_pkg.fish_audio import get_fish_audio

            self._fish = get_fish_audio()
        return self._fish

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
            text = await self.yandex.transcribe(audio_bytes, content_type=content_type)
            if text:
                return text, "yandex"
        return None, "none"

    async def synthesize(
        self,
        text: str,
        *,
        voice: str = "madirus",
        tone: str = "warm",
        prefer: str = "auto",  # auto | elevenlabs | yandex | xtts | fish
    ) -> tuple[bytes | None, str]:
        # Fish Audio: облачный Джарвис — при voice=jarvis_fish или prefer=fish
        if prefer == "fish" or voice == "jarvis_fish":
            fish = self._get_fish()
            if fish.is_configured():
                audio = await fish.synthesize(text, tone=tone)
                if audio:
                    return audio, "fish"

        # XTTS: локальный Джарвис — при voice=jarvis_local или prefer=xtts
        if prefer == "xtts" or voice == "jarvis_local":
            xtts = self._get_xtts()
            if xtts.is_available():
                audio = await xtts.synthesize_to_ogg(text)
                if audio:
                    return audio, "xtts"

        if prefer in ("auto", "elevenlabs") and Config.ELEVENLABS_API_KEY:
            audio = await self._get_eleven().synthesize(text, tone=tone)
            if audio:
                return audio, "elevenlabs"
        if Config.YANDEX_API_KEY:
            audio = await self.yandex.synthesize(text, voice=voice, tone=tone)
            if audio:
                return audio, "yandex"

        # Fallback chain: Fish Audio → XTTS
        fish = self._get_fish()
        if fish.is_configured():
            audio = await fish.synthesize(text, tone=tone)
            if audio:
                return audio, "fish"
        xtts = self._get_xtts()
        if xtts.is_available():
            audio = await xtts.synthesize_to_ogg(text)
            if audio:
                return audio, "xtts"

        return None, "none"

    async def synthesize_stream(
        self,
        text: str,
        *,
        voice: str = "madirus",
        tone: str = "warm",
    ) -> AsyncIterator[bytes]:
        # Fish Audio streaming для jarvis_fish
        if voice == "jarvis_fish":
            fish = self._get_fish()
            if fish.is_configured():
                async for chunk in fish.synthesize_stream(text, tone=tone):
                    yield chunk
                return

        # XTTS streaming для jarvis_local
        if voice == "jarvis_local":
            xtts = self._get_xtts()
            if xtts.is_available():
                async for chunk in xtts.synthesize_stream(text):
                    yield chunk
                return

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
        return YANDEX_VOICES

    # Backward-compat
    async def speech_to_text(self, audio_bytes: bytes, format: str = "ogg") -> str | None:  # noqa: ARG002
        text, _ = await self.transcribe(audio_bytes)
        return text

    async def text_to_speech(self, text: str, voice: str = "madirus") -> bytes | None:
        audio, _ = await self.synthesize(text, voice=voice)
        return audio
