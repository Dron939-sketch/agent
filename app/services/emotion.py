"""EmotionService: быстрый regex-детект + глубокий LLM-анализ.

Возвращает primary эмоцию из 8 (joy/sadness/anger/fear/surprise/calm/confusion/neutral),
интенсивность, подсказку тона ответа и флаг `needs_support`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

EMOTION_KEYWORDS: dict[str, tuple[str, ...]] = {
    "joy": ("счастлив", "рад", "отлично", "прекрасн", "замечательн", "круто", "ура", "люблю"),
    "sadness": ("груст", "печал", "тяжело", "плохо", "уныни", "тоск", "одинок", "скуч"),
    "anger": ("злюсь", "бес", "раздража", "ненавижу", "возмущ", "достал", "разъяр"),
    "fear": ("боюсь", "страшно", "тревожно", "волнуюсь", "опаса", "паник", "пугает"),
    "surprise": ("удивит", "неожиданн", "ничего себе", "вот это да", "ого", "вау"),
    "calm": ("спокой", "умиротвор", "расслаб", "тих", "хорошо мне"),
    "confusion": ("не понимаю", "запутал", "странно", "непонятн", "что вообще"),
}

NEEDS_SUPPORT = {"sadness", "fear", "anger"}

VALID_EMOTIONS = set(EMOTION_KEYWORDS.keys()) | {"neutral"}

TONE_BY_EMOTION: dict[str, str] = {
    "joy": "energetic",
    "sadness": "warm",
    "anger": "calm",
    "fear": "supportive",
    "surprise": "playful",
    "calm": "calm",
    "confusion": "clarifying",
    "neutral": "warm",
}


@dataclass(slots=True)
class EmotionResult:
    primary: str
    confidence: float
    intensity: int
    needs_support: bool
    tone: str
    scores: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "primary": self.primary,
            "confidence": round(self.confidence, 3),
            "intensity": self.intensity,
            "needs_support": self.needs_support,
            "tone": self.tone,
            "scores": {k: round(v, 3) for k, v in self.scores.items()},
        }


class EmotionService:
    """Эмоциональный анализ текста."""

    def __init__(self, llm_router: Any | None = None) -> None:
        self._router = llm_router

    def detect_from_text(self, text: str) -> EmotionResult:
        """Быстрая эвристика по ключевым словам (без сетевых вызовов)."""
        if not text:
            return EmotionResult("neutral", 0.3, 3, False, TONE_BY_EMOTION["neutral"])

        lower = text.lower()
        scores: dict[str, float] = {e: 0.0 for e in EMOTION_KEYWORDS}
        for emotion, keywords in EMOTION_KEYWORDS.items():
            for kw in keywords:
                if kw in lower:
                    scores[emotion] += 1.0

        total = sum(scores.values())
        if total == 0:
            return EmotionResult("neutral", 0.4, 3, False, TONE_BY_EMOTION["neutral"], scores)

        for k in scores:
            scores[k] = scores[k] / total

        primary = max(scores, key=lambda k: scores[k])
        confidence = scores[primary]
        intensity = min(10, max(1, int(round(confidence * 10))))
        return EmotionResult(
            primary=primary,
            confidence=confidence,
            intensity=intensity,
            needs_support=primary in NEEDS_SUPPORT,
            tone=TONE_BY_EMOTION.get(primary, "warm"),
            scores=scores,
        )

    async def detect_deep(self, text: str) -> EmotionResult:
        """Глубокий анализ через LLMRouter; на ошибке откатывается к regex."""
        if not self._router or not text:
            return self.detect_from_text(text)

        from app.services.llm import ChatMessage  # локальный импорт чтобы избежать циклов

        prompt = (
            "Проанализируй эмоциональное состояние пользователя по тексту. "
            "Ответь СТРОГО JSON без обёрток:\n"
            '{"primary": "joy|sadness|anger|fear|surprise|calm|confusion|neutral",'
            ' "intensity": 1-10, "tone": "warm|calm|energetic|supportive|playful|clarifying"}'
        )
        messages = [
            ChatMessage(role="system", content=prompt),
            ChatMessage(role="user", content=text[:2000]),
        ]
        try:
            resp = await self._router.chat(messages, profile="fast", temperature=0.2, max_tokens=120)  # type: ignore[arg-type]
            extracted = _extract_json(resp.text)
            data = json.loads(extracted) if extracted else {}
            primary = str(data.get("primary") or "")
            # Если LLM вернул мусор/пустоту/неизвестную эмоцию — fallback на regex
            if primary not in VALID_EMOTIONS:
                logger.debug("EmotionService deep returned invalid primary, falling back")
                return self.detect_from_text(text)
            intensity = int(data.get("intensity", 5))
            tone = str(data.get("tone") or TONE_BY_EMOTION.get(primary, "warm"))
            return EmotionResult(
                primary=primary,
                confidence=min(1.0, intensity / 10),
                intensity=intensity,
                needs_support=primary in NEEDS_SUPPORT,
                tone=tone,
            )
        except Exception as exc:
            logger.warning("EmotionService deep failed: %s", exc)
            return self.detect_from_text(text)


def _extract_json(text: str) -> str:
    """Достаёт первый {...} из ответа модели."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return ""
    return text[start : end + 1]
