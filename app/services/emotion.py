"""EmotionService: regex-detect + LLM-deep по 24-эмоциональному колесу Plutchik.

Колесо Плутчика: 8 базовых эмоций × 3 интенсивности = 24 оттенка.
- Joy: serenity, joy, ecstasy
- Trust: acceptance, trust, admiration
- Fear: apprehension, fear, terror
- Surprise: distraction, surprise, amazement
- Sadness: pensiveness, sadness, grief
- Disgust: boredom, disgust, loathing
- Anger: annoyance, anger, rage
- Anticipation: interest, anticipation, vigilance

Плюс производные: love (joy+trust), submission (trust+fear), awe (fear+surprise),
disapproval (surprise+sadness), remorse (sadness+disgust), contempt (disgust+anger),
aggressiveness (anger+anticipation), optimism (anticipation+joy), confusion, calm, neutral.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

# Базовые эмоции с keywords (русский). Каждая категория содержит триггеры
# от мягких (низкая интенсивность) до сильных (высокая).
EMOTION_KEYWORDS: dict[str, tuple[str, ...]] = {
    # Радость
    "joy": ("счастлив", "рад", "отлично", "прекрасн", "замечательн", "круто", "ура", "люблю", "восторг"),
    "ecstasy": ("кайф", "блаженств", "эйфори", "обожаю", "офигенно", "невероятно", "потрясающе"),
    "serenity": ("умиротвор", "благодарн", "довол", "приятно"),
    # Печаль
    "sadness": ("груст", "печал", "тяжело", "плохо", "уныни", "одинок"),
    "grief": ("горе", "трагеди", "невыносим", "разбит", "опустошен", "потеря"),
    "pensiveness": ("задумчив", "меланхол", "скуч", "тоск"),
    # Гнев
    "anger": ("злюсь", "бес", "раздража", "ненавижу", "возмущ"),
    "rage": ("ярость", "взбешен", "разъяр", "взрыв", "ненавиж", "рассвирепел"),
    "annoyance": ("раздражен", "досад", "достал", "надоел"),
    # Страх
    "fear": ("боюсь", "страшно", "тревожно", "волнуюсь", "опаса", "пугает"),
    "terror": ("ужас", "паник", "в шоке", "кошмар", "оцепенел"),
    "apprehension": ("неловко", "тревога", "беспоко", "сомнев"),
    # Удивление
    "surprise": ("удивит", "неожиданн", "ничего себе", "ого", "вау"),
    "amazement": ("ошеломл", "поразительно", "охренеть", "обалд", "офигел"),
    "distraction": ("странно", "необычно", "хм"),
    # Доверие
    "trust": ("верю", "доверяю", "надеюсь", "согласен", "конечно"),
    "admiration": ("восхищ", "уважаю", "горжус", "обожаю"),
    "acceptance": ("принимаю", "ладно", "хорошо", "ок"),
    # Отвращение
    "disgust": ("отврат", "противно", "мерзко", "гадко", "тошно"),
    "loathing": ("ненавиж", "омерзит", "презираю"),
    "boredom": ("скучно", "ску́шн", "уныло", "монотонн"),
    # Ожидание
    "anticipation": ("жду", "предвкуш", "интересно", "любопытно"),
    "vigilance": ("настороже", "внимательно", "следить"),
    "interest": ("инте", "увлек", "захватыв"),
    # Производные / композитные
    "love": ("люблю тебя", "влюблён", "влюблена", "нежност", "сердце", "родной"),
    "remorse": ("сожале", "виноват", "стыдно", "извин"),
    "contempt": ("презираю", "пофиг", "плевать"),
    "optimism": ("получится", "верю в", "всё будет", "обязательно"),
    "confusion": ("не понимаю", "запутал", "странно", "непонятн", "что вообще"),
    "calm": ("спокой", "расслаб", "тих", "хорошо мне"),
}

# Эмоции, при которых пользователю нужна поддержка
NEEDS_SUPPORT = {
    "sadness", "grief", "pensiveness",
    "fear", "terror", "apprehension",
    "anger", "rage", "annoyance",
    "disgust", "loathing", "remorse",
}

VALID_EMOTIONS = set(EMOTION_KEYWORDS.keys()) | {"neutral"}

# Тон ответа в зависимости от эмоции
TONE_BY_EMOTION: dict[str, str] = {
    # Радостные → энергично/тепло
    "joy": "energetic", "ecstasy": "energetic", "serenity": "warm",
    # Печальные → тепло, мягко
    "sadness": "warm", "grief": "supportive", "pensiveness": "warm",
    # Гневные → спокойно, не подливать масла
    "anger": "calm", "rage": "calm", "annoyance": "calm",
    # Страх → поддерживающе, размеренно
    "fear": "supportive", "terror": "supportive", "apprehension": "calm",
    # Удивление → играюче
    "surprise": "playful", "amazement": "playful", "distraction": "warm",
    # Доверие → тепло
    "trust": "warm", "admiration": "warm", "acceptance": "warm",
    # Отвращение → нейтрально
    "disgust": "calm", "loathing": "calm", "boredom": "energetic",
    # Ожидание → энергично
    "anticipation": "energetic", "vigilance": "calm", "interest": "energetic",
    # Композитные
    "love": "warm", "remorse": "supportive", "contempt": "calm",
    "optimism": "energetic", "confusion": "clarifying", "calm": "calm",
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
            "scores": {k: round(v, 3) for k, v in self.scores.items() if v > 0},
        }


class EmotionService:
    """Эмоциональный анализ текста (Plutchik 24-wheel)."""

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

        from app.services.llm import ChatMessage

        emotion_list = ", ".join(sorted(VALID_EMOTIONS))
        prompt = (
            "Проанализируй эмоциональное состояние пользователя по тексту. "
            "Используй колесо Плутчика (24 эмоции). "
            f"Допустимые primary: {emotion_list}. "
            "Ответь СТРОГО JSON без обёрток:\n"
            '{"primary": "...", "intensity": 1-10, '
            '"tone": "warm|calm|energetic|supportive|playful|clarifying"}'
        )
        messages = [
            ChatMessage(role="system", content=prompt),
            ChatMessage(role="user", content=text[:2000]),
        ]
        try:
            resp = await self._router.chat(
                messages, profile="fast", temperature=0.2, max_tokens=120
            )  # type: ignore[arg-type]
            extracted = _extract_json(resp.text)
            data = json.loads(extracted) if extracted else {}
            primary = str(data.get("primary") or "")
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
