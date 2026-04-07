"""Настройка логирования приложения."""

from __future__ import annotations

import logging
from typing import Optional

from .config import Config

_CONFIGURED = False


def setup_logging(level: Optional[str] = None) -> None:
    """Идемпотентная настройка корневого логгера."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    Config.ensure_dirs()
    # Python logging принимает только UPPERCASE либо int, а env-переменные
    # часто приходят как "info"/"debug" — нормализуем.
    resolved = (level or Config.LOG_LEVEL or "INFO").upper()
    if resolved not in {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"}:
        resolved = "INFO"

    logging.basicConfig(
        level=resolved,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(Config.LOGS_DIR / "assistant.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Возвращает настроенный логгер."""
    setup_logging()
    return logging.getLogger(name)
