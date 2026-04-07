"""Детект явных команд пользователя в чате.

Три типа intent'ов, которые мы обрабатываем без LLM:
- forget: «забудь X», «удали X из памяти»
- remember: «запомни что X», «не забудь X»
- list_memory: «что ты помнишь обо мне»
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

IntentType = Literal["forget", "remember", "list_memory", "none"]


@dataclass(slots=True)
class Intent:
    type: IntentType
    payload: str = ""


_FORGET_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?i)\bзабудь(?:\s+(?:что|про|о))?\s+(.+)$"),
    re.compile(r"(?i)\bудали(?:\s+из\s+памяти)?\s+(.+)$"),
    re.compile(r"(?i)\bне\s+помни\s+(.+)$"),
]

_REMEMBER_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?i)\bзапомни(?:\s+что)?\s+(.+)$"),
    re.compile(r"(?i)\bне\s+забудь(?:\s+что)?\s+(.+)$"),
    re.compile(r"(?i)\bвот\s+факт:?\s+(.+)$"),
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

    for pat in _FORGET_PATTERNS:
        m = pat.search(stripped)
        if m:
            return Intent(type="forget", payload=m.group(1).strip().rstrip(".!?"))

    for pat in _REMEMBER_PATTERNS:
        m = pat.search(stripped)
        if m:
            return Intent(type="remember", payload=m.group(1).strip().rstrip(".!?"))

    for pat in _LIST_PATTERNS:
        if pat.search(stripped):
            return Intent(type="list_memory")

    return Intent(type="none")
