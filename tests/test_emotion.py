"""Тесты EmotionService (regex + LLM-deep mock)."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from app.services.emotion import EmotionService
from app.services.llm import ChatResponse, LLMRouter, Usage


def test_detect_joy() -> None:
    r = EmotionService().detect_from_text("Я очень счастлив, всё прекрасно!")
    assert r.primary == "joy"
    assert r.needs_support is False
    assert r.tone == "energetic"


def test_detect_sadness_needs_support() -> None:
    r = EmotionService().detect_from_text("Мне очень грустно и тяжело сегодня")
    assert r.primary == "sadness"
    assert r.needs_support is True


def test_detect_anger() -> None:
    r = EmotionService().detect_from_text("Бесит всё это, ненавижу")
    assert r.primary == "anger"
    assert r.needs_support is True
    assert r.tone == "calm"


def test_detect_neutral_when_empty() -> None:
    r = EmotionService().detect_from_text("")
    assert r.primary == "neutral"
    assert r.intensity >= 1


def test_intensity_in_range() -> None:
    r = EmotionService().detect_from_text("отлично прекрасно радостно")
    assert 1 <= r.intensity <= 10


class _FakeClient:
    name = "fake"
    model = "fake-1"

    def __init__(self, payload: str) -> None:
        self.payload = payload

    async def chat(self, messages, *, temperature=0.7, max_tokens=2000):
        return ChatResponse(text=self.payload, model=self.model, usage=Usage())

    async def stream(self, messages, *, temperature=0.7, max_tokens=2000) -> AsyncIterator[str]:
        if False:
            yield ""


@pytest.mark.asyncio
async def test_detect_deep_uses_llm_json() -> None:
    client = _FakeClient('{"primary": "fear", "intensity": 8, "tone": "supportive"}')
    router = LLMRouter(profiles={"fast": [client]})
    r = await EmotionService(router).detect_deep("Мне очень страшно")
    assert r.primary == "fear"
    assert r.intensity == 8
    assert r.tone == "supportive"
    assert r.needs_support is True


@pytest.mark.asyncio
async def test_detect_deep_falls_back_on_bad_json() -> None:
    client = _FakeClient("not a json at all")
    router = LLMRouter(profiles={"fast": [client]})
    r = await EmotionService(router).detect_deep("Мне очень страшно")
    # Должен откатиться к regex и вернуть fear
    assert r.primary == "fear"
