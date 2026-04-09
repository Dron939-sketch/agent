#!/usr/bin/env python3
"""Скрипт подготовки голоса Джарвиса для XTTS.

Использование:
  python scripts/setup_jarvis_voice.py

Что делает:
1. Проверяет установку TTS и torch
2. Создаёт директорию data/voices/
3. Генерирует reference audio из встроенного TTS (если нет своего сэмпла)
4. Тестирует генерацию голоса

Для лучшего качества:
  Замените data/voices/jarvis.wav на 6-15 секунд чистого аудио
  голоса Paul Bettany (из интервью или фильма).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VOICE_DIR = ROOT / "data" / "voices"
JARVIS_WAV = VOICE_DIR / "jarvis.wav"


def check_deps() -> bool:
    """Проверяет зависимости."""
    missing = []
    try:
        import TTS  # noqa: F401
    except ImportError:
        missing.append("TTS")
    try:
        import torch  # noqa: F401
    except ImportError:
        missing.append("torch")

    if missing:
        print(f"❌ Не хватает зависимостей: {', '.join(missing)}")
        print(f"   Установи: pip install {' '.join(missing)} torchaudio")
        return False

    import torch
    device = "GPU ✅ " + torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU ⚠️  (будет медленнее)"
    print(f"✅ Зависимости OK. Устройство: {device}")
    return True


def create_reference_audio() -> bool:
    """Создаёт reference audio для клонирования."""
    VOICE_DIR.mkdir(parents=True, exist_ok=True)

    if JARVIS_WAV.exists():
        size_kb = JARVIS_WAV.stat().st_size / 1024
        print(f"✅ Reference audio уже есть: {JARVIS_WAV} ({size_kb:.0f} KB)")
        return True

    print("⚠️  Reference audio не найдено. Создаю placeholder...")
    print()
    print("   Для НАСТОЯЩЕГО голоса Джарвиса:")
    print("   1. Найди 6-15 секунд чистого аудио Paul Bettany")
    print("      (интервью, трейлеры Iron Man, YouTube)")
    print("   2. Сохрани как data/voices/jarvis.wav (моно, 22050 Hz)")
    print("   3. Перезапусти скрипт")
    print()

    # Генерируем placeholder через стандартный TTS (не клон, но рабочий)
    try:
        from TTS.api import TTS

        print("   Пока создаю placeholder с похожим стилем...")
        tts = TTS(model_name="tts_models/en/ljspeech/tacotron2-DDC")

        # Генерируем reference audio с "AI-ассистентским" тоном
        tts.tts_to_file(
            text="Good evening, sir. I have prepared the latest diagnostics for you. "
                 "All systems are operating within normal parameters. "
                 "Shall I proceed with the analysis?",
            file_path=str(JARVIS_WAV),
        )
        print(f"✅ Placeholder создан: {JARVIS_WAV}")
        print("   (замени на настоящий сэмпл Paul Bettany для лучшего качества)")
        return True
    except Exception as exc:
        print(f"❌ Не удалось создать placeholder: {exc}")
        print("   Положи свой WAV файл в data/voices/jarvis.wav")
        return False


def test_synthesis() -> bool:
    """Тестирует генерацию голоса."""
    if not JARVIS_WAV.exists():
        print("⏭  Пропускаю тест — нет reference audio")
        return False

    print("\n🧪 Тестирую XTTS синтез...")
    try:
        from TTS.api import TTS
        import torch
        import time

        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"   Загрузка XTTS v2 на {device}...")

        tts = TTS(model_name="tts_models/multilingual/multi-dataset/xtts_v2")
        if device == "cuda":
            tts.to("cuda")

        test_text = "Добрый вечер, сэр. Все системы работают в штатном режиме."
        output_path = str(VOICE_DIR / "jarvis_test.wav")

        print(f"   Генерирую: \"{test_text}\"")
        start = time.time()

        tts.tts_to_file(
            text=test_text,
            file_path=output_path,
            speaker_wav=str(JARVIS_WAV),
            language="ru",
        )

        elapsed = time.time() - start
        size_kb = Path(output_path).stat().st_size / 1024

        print(f"✅ Тест пройден! ({elapsed:.1f}с, {size_kb:.0f} KB)")
        print(f"   Результат: {output_path}")
        print(f"   Скорость: {'🚀 real-time' if elapsed < 3 else '🐢 медленно (нужен GPU)'}")
        return True

    except Exception as exc:
        print(f"❌ Тест провалился: {exc}")
        return False


def main() -> None:
    print("=" * 50)
    print("  🤖 Настройка голоса Джарвиса для Фреди")
    print("=" * 50)
    print()

    if not check_deps():
        sys.exit(1)

    print()
    create_reference_audio()
    test_synthesis()

    print()
    print("=" * 50)
    print("  Готово! Голос Джарвиса настроен.")
    print()
    print("  Env-переменные:")
    print("    XTTS_DEVICE=auto       (auto/cuda/cpu)")
    print(f"    XTTS_SPEAKER_WAV={JARVIS_WAV}")
    print()
    print("  Использование в коде:")
    print("    from app.services.voice_pkg.xtts import get_xtts")
    print("    audio = await get_xtts().synthesize('Привет, сэр.')")
    print("=" * 50)


if __name__ == "__main__":
    main()
