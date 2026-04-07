"""Загрузчик базы знаний (Markdown файлов из data/knowledge/).

Используется для инжекта персоны/манифеста в system prompt LLM.
Lazy + cached: читает с диска один раз за процесс.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from app.core.config import Config
from app.core.logging import get_logger

logger = get_logger(__name__)


@lru_cache(maxsize=1)
def kb_root() -> Path:
    return Config.BASE_DIR / "data" / "knowledge"


@lru_cache(maxsize=32)
def load_doc(name: str) -> str:
    """Читает Markdown-файл из data/knowledge/. Возвращает '' если нет."""
    path = kb_root() / name
    if not path.exists():
        # пробуем относительно cwd на случай нестандартного запуска
        alt = Path.cwd() / "data" / "knowledge" / name
        if alt.exists():
            path = alt
        else:
            logger.info("KB doc not found: %s", name)
            return ""
    try:
        return path.read_text(encoding="utf-8")
    except Exception as exc:
        logger.warning("Failed to read KB %s: %s", name, exc)
        return ""


@lru_cache(maxsize=1)
def freddy_persona() -> str:
    """Текст манифеста Фреди для system prompt."""
    return load_doc("freddy_persona.md")


def reset_cache() -> None:
    """Сброс кеша (для тестов или горячей перезагрузки KB)."""
    load_doc.cache_clear()
    freddy_persona.cache_clear()
    kb_root.cache_clear()
