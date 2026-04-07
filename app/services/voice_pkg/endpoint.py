"""SemanticEndpointDetector: эвристика «закончил ли пользователь мысль».

Без LLM, на чистых regex. Используется фронтом голосового режима, чтобы
понять, отправлять накопленный transcript серверу или ждать продолжения.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Маркеры незаконченной мысли (пользователь явно собирается продолжить)
INCOMPLETE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(
        r"(?i)\b(и|а|но|однако|потому что|так как|чтобы|для того чтобы|если|когда)\s*$"
    ),
    re.compile(r"(?i)\b(как|почему|зачем|где|куда|откуда|чей|какой|какая|какое)\s*$"),
    re.compile(r"(?i)\b(например|такой как|вроде|типа|в смысле)\s*$"),
    re.compile(r"(?i)\b(потом|затем|дальше|далее)\s*$"),
    re.compile(r"(?i)\b(во-первых|во-вторых|в-третьих)\s*$"),
    re.compile(r"\b\d+\s*$"),  # цифра в конце — вероятно перечисление
    re.compile(r"[,;:]\s*$"),
]

# Маркеры законченной мысли
COMPLETE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"[.!?…]\s*$"),
    re.compile(
        r"(?i)\b(спасибо|пожалуйста|вот так|так вот|короче|в общем|всё)\s*[.!?]?\s*$"
    ),
    re.compile(r"(?i)\b(да|нет|ладно|хорошо|понятно|ясно|ок)\s*[.!?]?\s*$"),
]


@dataclass(slots=True)
class EndpointResult:
    is_complete: bool
    confidence: float
    reason: str

    def to_dict(self) -> dict[str, object]:
        return {
            "is_complete": self.is_complete,
            "confidence": round(self.confidence, 3),
            "reason": self.reason,
        }


class SemanticEndpointDetector:
    """Чистый эвристический детектор без сетевых зависимостей."""

    def detect(self, text: str, *, silence_ms: int = 0) -> EndpointResult:
        if not text or len(text) < 3:
            return EndpointResult(False, 0.3, "empty")

        for pat in INCOMPLETE_PATTERNS:
            if pat.search(text):
                return EndpointResult(False, 0.85, f"incomplete:{pat.pattern[:30]}")

        for pat in COMPLETE_PATTERNS:
            if pat.search(text):
                return EndpointResult(True, 0.9, f"complete:{pat.pattern[:30]}")

        words = text.split()
        if silence_ms > 1500 and len(words) > 10:
            return EndpointResult(True, 0.75, "long_silence")

        if len(words) < 5:
            return EndpointResult(False, 0.6, "too_short")

        # По умолчанию считаем закончил (лучше отправить лишнее, чем виснуть)
        return EndpointResult(True, 0.55, "default")
