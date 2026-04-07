"""Тесты SemanticEndpointDetector + extractor + endpoint API."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from app.services.llm import ChatResponse, LLMRouter, Usage
from app.services.memory.extractor import extract_facts
from app.services.voice_pkg import SemanticEndpointDetector


# ============ SemanticEndpointDetector ============

def test_endpoint_complete_with_period() -> None:
    r = SemanticEndpointDetector().detect("Я работаю программистом.")
    assert r.is_complete is True
    assert r.confidence >= 0.8


def test_endpoint_incomplete_with_conjunction() -> None:
    r = SemanticEndpointDetector().detect("Я хочу пойти и")
    assert r.is_complete is False


def test_endpoint_incomplete_with_question_word() -> None:
    r = SemanticEndpointDetector().detect("я не понимаю как")
    assert r.is_complete is False


def test_endpoint_too_short() -> None:
    r = SemanticEndpointDetector().detect("ну вот")
    assert r.is_complete is False
    assert r.reason == "too_short"


def test_endpoint_long_silence_assumes_done() -> None:
    text = "это длинное сообщение из десяти разных слов без знаков препинания нигде"
    r = SemanticEndpointDetector().detect(text, silence_ms=2000)
    assert r.is_complete is True


def test_endpoint_default_for_medium_text() -> None:
    r = SemanticEndpointDetector().detect("я думаю над этой проблемой давно")
    # 6 слов, без знаков, без пауз → default = True
    assert r.is_complete is True
    assert r.reason == "default"


# ============ extract_facts ============


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
async def test_extract_facts_parses_json_array() -> None:
    payload = (
        '[{"fact": "Меня зовут Андрей", "type": "personal", "importance": 8},'
        ' {"fact": "Боюсь публичных выступлений", "type": "fear", "importance": 7}]'
    )
    router = LLMRouter(profiles={"fast": [_FakeClient(payload)]})
    facts = await extract_facts(
        router,
        [
            {"role": "user", "content": "Привет, меня зовут Андрей"},
            {"role": "assistant", "content": "Привет, Андрей!"},
            {"role": "user", "content": "Боюсь публичных выступлений"},
        ],
    )
    assert len(facts) == 2
    assert facts[0].fact.startswith("Меня зовут")
    assert facts[1].type == "fear"
    assert facts[1].importance == 7


@pytest.mark.asyncio
async def test_extract_facts_returns_empty_on_garbage() -> None:
    router = LLMRouter(profiles={"fast": [_FakeClient("полная дичь без скобок")]})
    facts = await extract_facts(router, [{"role": "user", "content": "x"}])
    assert facts == []


@pytest.mark.asyncio
async def test_extract_facts_handles_empty_history() -> None:
    router = LLMRouter(profiles={"fast": [_FakeClient("[]")]})
    facts = await extract_facts(router, [])
    assert facts == []
