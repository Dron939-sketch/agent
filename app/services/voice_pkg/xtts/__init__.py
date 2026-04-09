"""Coqui XTTS v2 — локальный TTS с клонированием голоса.

Бесплатный, self-hosted TTS-провайдер. Клонирует любой голос
с 6-секундного аудио-сэмпла. Поддерживает русский, английский,
и ещё 15 языков.

Требования:
  pip install TTS torch torchaudio
  GPU (CUDA) — рекомендуется для real-time (<2 сек)
  CPU — работает, но ~10-15 сек на фразу

Использование:
  Положите reference audio в data/voices/jarvis.wav
  Модель скачается автоматически при первом запуске (~1.8 ГБ)

Env:
  XTTS_DEVICE=cuda|cpu|auto  (default: auto)
  XTTS_SPEAKER_WAV=data/voices/jarvis.wav
"""

from __future__ import annotations

import io
import os
import time
import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

from app.core.logging import get_logger

logger = get_logger(__name__)

# Конфигурация
XTTS_DEVICE = os.environ.get("XTTS_DEVICE", "auto")
XTTS_SPEAKER_WAV = os.environ.get("XTTS_SPEAKER_WAV", "data/voices/jarvis.wav")
XTTS_MODEL_NAME = "tts_models/multilingual/multi-dataset/xtts_v2"

# Язык → код XTTS
LANG_MAP = {
    "ru": "ru",
    "en": "en",
    "ru-RU": "ru",
    "en-US": "en",
}


def _detect_device() -> str:
    """Определяет лучшее доступное устройство."""
    if XTTS_DEVICE != "auto":
        return XTTS_DEVICE
    try:
        import torch
        if torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0)
            logger.info("XTTS: GPU detected — %s", gpu_name)
            return "cuda"
    except ImportError:
        pass
    logger.info("XTTS: No GPU, using CPU (slower)")
    return "cpu"


class CoquiXTTS:
    """Локальный TTS через Coqui XTTS v2 с клонированием голоса.

    Ленивая инициализация — модель загружается только при первом вызове.
    """

    def __init__(
        self,
        speaker_wav: str | None = None,
        device: str | None = None,
        language: str = "ru",
    ) -> None:
        self.speaker_wav = speaker_wav or XTTS_SPEAKER_WAV
        self.device = device or _detect_device()
        self.language = LANG_MAP.get(language, "ru")
        self._tts = None
        self._available: bool | None = None

    def is_available(self) -> bool:
        """Проверяет доступность: библиотека установлена + есть speaker wav."""
        if self._available is not None:
            return self._available

        # Проверяем библиотеку
        try:
            import TTS  # noqa: F401
        except ImportError:
            logger.warning("XTTS unavailable: `pip install TTS torch torchaudio`")
            self._available = False
            return False

        # Проверяем reference audio
        if not Path(self.speaker_wav).exists():
            logger.warning(
                "XTTS: speaker wav not found at %s. "
                "Place a 6-15s audio sample there, or set XTTS_SPEAKER_WAV env.",
                self.speaker_wav,
            )
            self._available = False
            return False

        self._available = True
        return True

    def _load_model(self):
        """Загружает модель (при первом вызове). Может занять 30-60 сек."""
        if self._tts is not None:
            return self._tts

        logger.info("XTTS: Loading model (device=%s)... this may take a minute.", self.device)
        start = time.time()

        from TTS.api import TTS

        tts = TTS(model_name=XTTS_MODEL_NAME)
        if self.device == "cuda":
            tts.to("cuda")

        elapsed = time.time() - start
        logger.info("XTTS: Model loaded in %.1fs on %s", elapsed, self.device)
        self._tts = tts
        return tts

    async def synthesize(
        self,
        text: str,
        *,
        language: str | None = None,
        speaker_wav: str | None = None,
    ) -> bytes | None:
        """Генерирует аудио из текста с клонированным голосом.

        Returns: WAV bytes или None при ошибке.
        """
        if not self.is_available():
            return None

        lang = LANG_MAP.get(language or self.language, "ru")
        ref_wav = speaker_wav or self.speaker_wav

        def _generate() -> bytes:
            tts = self._load_model()

            # Генерируем в памяти (без файлов)
            import tempfile
            import wave

            with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as tmp:
                tts.tts_to_file(
                    text=text[:500],  # XTTS оптимален на коротких фразах
                    file_path=tmp.name,
                    speaker_wav=ref_wav,
                    language=lang,
                )
                tmp.seek(0)
                return tmp.read()

        try:
            start = time.time()
            # Запускаем в thread pool чтобы не блокировать event loop
            wav_bytes = await asyncio.get_event_loop().run_in_executor(None, _generate)
            elapsed = time.time() - start
            logger.info(
                "XTTS: synthesized %d chars in %.1fs (%s, %s)",
                len(text), elapsed, self.device, lang,
            )
            return wav_bytes
        except Exception as exc:
            logger.error("XTTS synthesis failed: %s", exc)
            return None

    async def synthesize_stream(
        self,
        text: str,
        *,
        language: str | None = None,
        speaker_wav: str | None = None,
        chunk_size: int = 4096,
    ) -> AsyncIterator[bytes]:
        """Streaming версия — отдаёт WAV чанками по мере генерации.

        Для XTTS настоящий streaming возможен только с GPU.
        На CPU — генерируем целиком, потом стримим чанками.
        """
        audio = await self.synthesize(
            text, language=language, speaker_wav=speaker_wav
        )
        if not audio:
            return

        # Отдаём чанками
        offset = 0
        while offset < len(audio):
            yield audio[offset:offset + chunk_size]
            offset += chunk_size

    async def synthesize_to_ogg(
        self,
        text: str,
        *,
        language: str | None = None,
        speaker_wav: str | None = None,
    ) -> bytes | None:
        """Генерирует OGG/Opus (совместимо с существующим TTS pipeline).

        Конвертирует WAV → OGG через ffmpeg или pydub.
        """
        wav = await self.synthesize(text, language=language, speaker_wav=speaker_wav)
        if not wav:
            return None

        def _convert() -> bytes:
            try:
                # Попытка через pydub (если установлен)
                from pydub import AudioSegment
                segment = AudioSegment.from_wav(io.BytesIO(wav))
                buf = io.BytesIO()
                segment.export(buf, format="ogg", codec="libopus")
                return buf.getvalue()
            except ImportError:
                pass

            try:
                # Попытка через ffmpeg напрямую
                import subprocess
                result = subprocess.run(
                    ["ffmpeg", "-i", "pipe:0", "-c:a", "libopus", "-f", "ogg", "pipe:1"],
                    input=wav,
                    capture_output=True,
                    timeout=30,
                )
                if result.returncode == 0:
                    return result.stdout
            except FileNotFoundError:
                pass

            # Fallback: возвращаем WAV
            logger.warning("XTTS: cannot convert to OGG (install pydub or ffmpeg)")
            return wav

        return await asyncio.get_event_loop().run_in_executor(None, _convert)


# === Singleton ===

_instance: CoquiXTTS | None = None


def get_xtts() -> CoquiXTTS:
    global _instance
    if _instance is None:
        _instance = CoquiXTTS()
    return _instance
