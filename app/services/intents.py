"""Детект явных команд пользователя в чате."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

IntentType = Literal["forget", "remember", "list_memory", "none"]


@dataclass(slots=True)
class Intent:
    type: IntentType
    payload: str = ""


# Разрешаем запятые, двоеточия и пробелы после ключевого глагола.
_FORGET_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?i)\bзабудь[,:\s]+(?:что|про|о[бв]?)?[,:\s]*(.+)$"),
    re.compile(r"(?i)\bудали[,:\s]+(?:из\s+памяти[,:\s]+)?(.+)$"),
    re.compile(r"(?i)\bне\s+помни[,:\s]+(.+)$"),
]

_REMEMBER_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?i)\bзапомни[,:\s]+(?:что[,:\s]+)?(.+)$"),
    re.compile(r"(?i)\bне\s+забудь[,:\s]+(?:что[,:\s]+)?(.+)$"),
    re.compile(r"(?i)\bвот\s+факт[,:\s]+(.+)$"),
]

_LIST_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?i)что\s+ты\s+помнишь\s+обо\s+мне\??$"),
    re.compile(r"(?i)что\s+ты\s+знаешь\s+обо\s+мне\??$"),
    re.compile(r"(?i)покажи\s+(?:мою\s+)?память"),
]


def detect_intent(text: str) -> Intent:
    """Возвращает Intent. Если ничего не подошло — type='none'."""
    if not text:
        return Intent(type="none")

    stripped = text.strip()

    # Сначала remember (т.к. «не забудь» содержит «забудь» — pattern для
    # remember более специфичен и должен проверяться раньше).
    for pat in _REMEMBER_PATTERNS:
        m = pat.search(stripped)
        if m:
            return Intent(type="remember", payload=m.group(1).strip().rstrip(".!?"))

    for pat in _FORGET_PATTERNS:
        m = pat.search(stripped)
        if m:
            return Intent(type="forget", payload=m.group(1).strip().rstrip(".!?"))

    for pat in _LIST_PATTERNS:
        if pat.search(stripped):
            return Intent(type="list_memory")

    return Intent(type="none")
