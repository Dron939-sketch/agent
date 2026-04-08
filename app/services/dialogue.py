"""Dialogue state machine: уточнения, подтверждения, многоходовый диалог.

Sprint 11: Фреди умеет задавать уточняющие вопросы когда запрос неоднозначен,
запрашивать подтверждение перед важными действиями, и вести связный
многоходовый диалог.

Интегрируется в system prompt через дополнительные инструкции.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from app.core.logging import get_logger

logger = get_logger(__name__)


class DialogueState(str, Enum):
    """Состояние текущего диалога."""
    OPEN = "open"                   # Свободный разговор
    AWAITING_CLARIFICATION = "clarification"  # Ждём уточнения
    AWAITING_CONFIRMATION = "confirmation"    # Ждём подтверждения (да/нет)
    TASK_IN_PROGRESS = "task"       # Выполняем многоходовую задачу


@dataclass(slots=True)
class ClarificationNeed:
    """Описывает необходимость уточнения."""
    needed: bool
    reason: str = ""
    question: str = ""  # Предлагаемый уточняющий вопрос
    options: list[str] | None = None  # Варианты для выбора


# Паттерны неоднозначных запросов
_AMBIGUOUS_PATTERNS = [
    # Слишком короткий запрос без контекста
    (re.compile(r"^(сделай|покажи|найди|открой|запусти)\s*$", re.I), "Что именно?"),
    # "Это" / "то" без ясного антецедента
    (re.compile(r"^(это|то|тот|та|те)\b", re.I), "Уточни, о чём идёт речь?"),
    # "Как обычно" — может быть неясно
    (re.compile(r"как\s+обычно", re.I), None),  # проверяем есть ли в памяти
]

# Паттерны запросов требующих подтверждения (потенциально опасные действия)
_CONFIRM_PATTERNS = [
    re.compile(r"(?i)удали\s+(все|всё|всех)", re.I),
    re.compile(r"(?i)забудь\s+(все|всё|обо\s+мне)", re.I),
    re.compile(r"(?i)отмени\s+(все|всё)\s+(задачи|напоминания|цели)", re.I),
    re.compile(r"(?i)отправь\s+(письмо|сообщение|email)", re.I),
]

# Подтверждения
_YES_PATTERNS = re.compile(r"(?i)^(да|ага|угу|конечно|давай|подтверждаю|yes|yep|ок|хорошо|верно)\s*[.!]?$")
_NO_PATTERNS = re.compile(r"(?i)^(нет|не|отмена|отмени|cancel|no|nope|неа)\s*[.!]?$")


def detect_clarification_need(
    message: str,
    history: list[dict[str, str]] | None = None,
) -> ClarificationNeed:
    """Определяет нужно ли уточнение перед ответом."""
    stripped = message.strip()

    # Слишком короткий запрос (< 3 слова)
    words = stripped.split()
    if 1 <= len(words) <= 2 and not _YES_PATTERNS.match(stripped) and not _NO_PATTERNS.match(stripped):
        for pat, question in _AMBIGUOUS_PATTERNS:
            if pat.search(stripped):
                return ClarificationNeed(
                    needed=True,
                    reason="ambiguous_command",
                    question=question or f"Уточни, что именно ты имеешь в виду: «{stripped}»?",
                )

    return ClarificationNeed(needed=False)


def needs_confirmation(message: str) -> ClarificationNeed:
    """Проверяет требует ли действие подтверждения."""
    for pat in _CONFIRM_PATTERNS:
        if pat.search(message):
            return ClarificationNeed(
                needed=True,
                reason="dangerous_action",
                question=f"Ты уверен? Это действие может быть необратимым.",
            )
    return ClarificationNeed(needed=False)


def is_confirmation(message: str) -> bool | None:
    """Проверяет является ли сообщение подтверждением.

    Returns: True (да), False (нет), None (непонятно).
    """
    stripped = message.strip()
    if _YES_PATTERNS.match(stripped):
        return True
    if _NO_PATTERNS.match(stripped):
        return False
    return None


def build_dialogue_instructions(
    history: list[dict[str, str]] | None = None,
) -> str:
    """Генерирует инструкции для LLM по ведению диалога.

    Добавляется в system prompt для улучшения качества диалога.
    """
    instructions = [
        "ПРАВИЛА ДИАЛОГА:",
        "- Если запрос пользователя неоднозначен — задай ОДИН уточняющий вопрос вместо угадывания.",
        "- Если действие может быть необратимым — попроси подтверждение.",
        "- Если пользователь ответил коротко (да/нет/ок) — смотри контекст предыдущих сообщений.",
        "- Не задавай больше одного вопроса за раз.",
        "- Если у тебя есть предположение — предложи его: «Ты имеешь в виду X? Или Y?»",
        "- Помни предыдущий контекст разговора и ссылайся на него.",
    ]

    # Проверяем есть ли незакрытый вопрос в истории
    if history and len(history) >= 2:
        last_assistant = None
        for msg in reversed(history):
            if msg["role"] == "assistant":
                last_assistant = msg["content"]
                break
        if last_assistant and last_assistant.rstrip().endswith("?"):
            instructions.append("- ВАЖНО: Ты задал вопрос в предыдущем сообщении. Если пользователь отвечает — учти контекст вопроса.")

    return "\n".join(instructions)
