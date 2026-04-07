"""Varitype Knowledge Base → фрагмент system prompt с профилем пользователя."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.core.config import Config
from app.core.logging import get_logger

logger = get_logger(__name__)

KB_FILENAME = "varitype-kb-v2.json"


@lru_cache(maxsize=1)
def load_kb(path: str | None = None) -> dict[str, Any]:
    """Лениво читает KB с диска. Ищет файл в корне репо."""
    candidates = []
    if path:
        candidates.append(Path(path))
    candidates.append(Config.BASE_DIR / KB_FILENAME)
    candidates.append(Path.cwd() / KB_FILENAME)
    for p in candidates:
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.warning("Failed to parse %s: %s", p, exc)
                return {}
    logger.info("Varitype KB not found, returning empty dict")
    return {}


def describe_vector(kb: dict[str, Any], code: str, level: int) -> dict[str, Any]:
    """Возвращает словарь с описанием вектора на заданном уровне (1-6)."""
    vectors = kb.get("vectors", {})
    vec = vectors.get(code, {})
    if not vec:
        return {}
    levels = vec.get("levels", {})
    level_data = levels.get(str(level), {})
    return {
        "name": vec.get("name"),
        "essence": vec.get("essence"),
        "language": vec.get("language"),
        "level_name": level_data.get("name"),
        "what_they_need": level_data.get("what_they_need"),
        "how_to_lead": level_data.get("how_to_lead"),
    }


def build_profile_prompt(profile: dict[str, Any], kb: dict[str, Any] | None = None) -> str:
    """Строит системный фрагмент с описанием доминанты пользователя.

    `kb=None` → пытается загрузить с диска. Передача `kb={}` намеренно
    отключает загрузку (используется в тестах) и возвращает пустую строку.
    """
    if kb is None:
        kb = load_kb()
    if not profile or not kb:
        return ""

    dominant = profile.get("dominant")
    if not dominant:
        return ""
    level = int(profile.get(dominant, 3) or 3)
    info = describe_vector(kb, dominant, level)
    if not info:
        return ""

    lines = [
        "ПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ (Varitype):",
        f"- Доминанта: {dominant} — {info.get('name', '')}",
        f"- Уровень: {level} ({info.get('level_name', '')})",
        f"- Суть: {info.get('essence', '')}",
        f"- Тип восприятия: {profile.get('perception_type', '—')}",
        f"- Уровень мышления: {profile.get('thinking_level', '—')}/9",
    ]
    if info.get("language"):
        lines.append(f"- Предпочитает речь: {info['language']}")
    if info.get("what_they_need"):
        lines.append(f"- Что реально нужно: {info['what_they_need']}")
    if info.get("how_to_lead"):
        lines.append(f"- Как вести: {info['how_to_lead']}")
    lines.append("Учитывай эти особенности в тоне, длине и глубине ответа.")
    return "\n".join(lines)
