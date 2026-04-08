"""Детект явных команд пользователя в чате.

ROUND 1: добавлены coach intents — goal_set / habit_create / habit_check.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

IntentType = Literal[
    "forget",
    "remember",
    "list_memory",
    "goal_set",
    "goal_list",
    "habit_create",
    "habit_check",
    "habit_list",
    "none",
]


@dataclass(slots=True)
class Intent:
    type: IntentType
    payload: str = ""


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

# === ROUND 1: Coach intents ===
_GOAL_SET_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?i)\b(?:моя\s+)?цель[,:\s—-]+(.+)$"),
    re.compile(r"(?i)\bхочу\s+(?:достичь|добиться|достигнуть)[,:\s]+(.+)$"),
    re.compile(r"(?i)\bпоставь\s+(?:мне\s+)?цель[,:\s]+(.+)$"),
]

_GOAL_LIST_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?i)(?:покажи|расскажи)\s+(?:мои\s+)?цели"),
    re.compile(r"(?i)какие\s+у\s+меня\s+цели"),
    re.compile(r"(?i)список\s+целей"),
]

_HABIT_CREATE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?i)\bновая\s+привычка[,:\s—-]+(.+)$"),
    re.compile(r"(?i)\bхочу\s+(?:приучить|приучаться|приучить\s+себя)\s+(.+)$"),
    re.compile(r"(?i)\bбуду\s+(?:каждый\s+день|ежедневно)\s+(.+)$"),
    re.compile(r"(?i)\bдобавь\s+привычку[,:\s]+(.+)$"),
]

_HABIT_CHECK_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?i)\b(?:сделал|сделала|выполнил|выполнила|готово)[,:\s—-]+(.+)$"),
    re.compile(r"(?i)\bотметь\s+(?:что\s+я\s+)?(.+)$"),
    re.compile(r"(?i)\bвыполнил\s+привычку[,:\s]+(.+)$"),
]

_HABIT_LIST_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?i)(?:покажи|расскажи)\s+(?:мои\s+)?привычки"),
    re.compile(r"(?i)какие\s+у\s+меня\s+привычки"),
    re.compile(r"(?i)список\s+привычек"),
]


def detect_intent(text: str) -> Intent:
    """Возвращает Intent. Если ничего не подошло — type='none'."""
    if not text:
        return Intent(type="none")

    stripped = text.strip()

    # Список — без payload
    for pat in _GOAL_LIST_PATTERNS:
        if pat.search(stripped):
            return Intent(type="goal_list")
    for pat in _HABIT_LIST_PATTERNS:
        if pat.search(stripped):
            return Intent(type="habit_list")
    for pat in _LIST_PATTERNS:
        if pat.search(stripped):
            return Intent(type="list_memory")

    # remember проверяется раньше forget (т.к. «не забудь» содержит «забудь»)
    for pat in _REMEMBER_PATTERNS:
        m = pat.search(stripped)
        if m:
            return Intent(type="remember", payload=m.group(1).strip().rstrip(".!?"))

    for pat in _FORGET_PATTERNS:
        m = pat.search(stripped)
        if m:
            return Intent(type="forget", payload=m.group(1).strip().rstrip(".!?"))

    # Coach intents
    for pat in _HABIT_CREATE_PATTERNS:
        m = pat.search(stripped)
        if m:
            return Intent(type="habit_create", payload=m.group(1).strip().rstrip(".!?"))

    for pat in _HABIT_CHECK_PATTERNS:
        m = pat.search(stripped)
        if m:
            return Intent(type="habit_check", payload=m.group(1).strip().rstrip(".!?"))

    for pat in _GOAL_SET_PATTERNS:
        m = pat.search(stripped)
        if m:
            return Intent(type="goal_set", payload=m.group(1).strip().rstrip(".!?"))

    return Intent(type="none")
