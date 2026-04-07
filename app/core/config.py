"""Конфигурация приложения.

Извлечено из монолитного main.py в рамках Фазы 1 рефакторинга.
В будущем будет заменено на pydantic-settings.
"""

from __future__ import annotations

import os
import secrets
from functools import lru_cache
from pathlib import Path


class Config:
    """Глобальная конфигурация Фреди."""

    # === LLM провайдеры ===
    DEEPSEEK_API_KEY: str = os.environ.get("DEEPSEEK_API_KEY", "")
    ANTHROPIC_API_KEY: str = os.environ.get("ANTHROPIC_API_KEY", "")
    OPENAI_API_KEY: str = os.environ.get("OPENAI_API_KEY", "")
    OLLAMA_BASE_URL: str = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")

    # === Внешние сервисы ===
    YANDEX_API_KEY: str = os.environ.get("YANDEX_API_KEY", "")
    OPENWEATHER_API_KEY: str = os.environ.get("OPENWEATHER_API_KEY", "")
    TAVILY_API_KEY: str = os.environ.get("TAVILY_API_KEY", "")

    # === GitHub ===
    GITHUB_TOKEN: str = os.environ.get("GITHUB_TOKEN", "")
    GITHUB_REPO: str = os.environ.get("GITHUB_REPO", "")

    # === Приложение ===
    APP_NAME: str = "Фреди AI Помощник"
    APP_VERSION: str = "5.1.0-dev"
    SECRET_KEY: str = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
    PORT: int = int(os.environ.get("PORT", 8000))
    LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO")

    # === Пути ===
    BASE_DIR: Path = Path(__file__).resolve().parents[2]
    DATA_DIR: Path = BASE_DIR / "data"
    BACKUP_DIR: Path = BASE_DIR / "backups"
    LOGS_DIR: Path = BASE_DIR / "logs"
    STATIC_DIR: Path = BASE_DIR / "static"
    DATABASE_PATH: Path = DATA_DIR / "assistant.db"

    # === Хранилища (целевые) ===
    DATABASE_URL: str = os.environ.get(
        "DATABASE_URL", f"sqlite+aiosqlite:///{DATABASE_PATH}"
    )
    REDIS_URL: str = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    QDRANT_URL: str = os.environ.get("QDRANT_URL", "http://localhost:6333")

    @classmethod
    def ensure_dirs(cls) -> None:
        """Создаёт обязательные директории при старте приложения."""
        for path in (cls.DATA_DIR, cls.BACKUP_DIR, cls.LOGS_DIR, cls.STATIC_DIR):
            path.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Config:
    """Singleton-доступ к конфигурации."""
    Config.ensure_dirs()
    return Config()
