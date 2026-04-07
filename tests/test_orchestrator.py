"""Тесты orchestrator: ReAct loop с фейковым LLM, использование tools, max_steps."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from app.orchestrator import ReActAgent, StepKind
from app.services.llm import ChatMessage, ChatResponse, LLMRouter, Usage
from app.services.tools import default_registry


class _ScriptedClient:
    """Фейковый LLM, отдающий заранее заданную последовательность ответов."""

    name = "scripted"
    model = "scripted-1"

    def __init__(self, replies: list[str]) -> None:
        self.replies = list(replies)
        self.calls: list[list[ChatMessage]] = []

    async def chat(self, messages, *, temperature=0.7, max_tokens=2000):
        self.calls.append(list(messages))
        if not self.replies:
            return ChatResponse(text="THOUGHT: done\nFINAL: empty", model=self.model, usage=Usage())
        return ChatResponse(text=self.replies.pop(0), model=self.model, usage=Usage())

    async def stream(self, messages, *, temperature=0.7, max_tokens=2000) -> AsyncIterator[str]:
        if False:
            yield ""


def _router(client: _ScriptedClient) -> LLMRouter:
    return LLMRouter(profiles={"smart": [client]})


@pytest.mark.asyncio
async def test_react_agent_uses_calculator_then_finals() -> None:
    client = _ScriptedClient(
        [
            'THOUGHT: нужно посчитать\nACTION: calculator\nARGS: {"expression": "2+2*3"}',
            "THOUGHT: получил 8\nFINAL: Ответ: 8",
        ]
    )
    agent = ReActAgent(
        name="Test",
        role_prompt="ты тестовый агент",
        router=_router(client),
        registry=default_registry(),
        profile="smart",
        max_steps=4,
    )
    answer, trace = await agent.run("Сколько 2+2*3?")
    assert "8" in answer
    kinds = [s.kind for s in trace.steps]
    assert StepKind.ACTION in kinds
    assert StepKind.OBSERVATION in kinds
    assert StepKind.FINAL in kinds
    obs = next(s for s in trace.steps if s.kind is StepKind.OBSERVATION)
    assert obs.content == "8"


@pytest.mark.asyncio
async def test_react_agent_max_steps_breaks_loop() -> None:
    client = _ScriptedClient(
        ['ACTION: calculator\nARGS: {"expression": "1+1"}'] * 10
    )
    agent = ReActAgent(
        name="Loopy",
        role_prompt="loop",
        router=_router(client),
        registry=default_registry(),
        max_steps=3,
    )
    answer, trace = await agent.run("loop forever")
    assert "max_steps" in answer
    actions = [s for s in trace.steps if s.kind is StepKind.ACTION]
    assert len(actions) == 3


@pytest.mark.asyncio
async def test_react_agent_invalid_format_recovers() -> None:
    client = _ScriptedClient(
        [
            "просто текст без формата",
            "THOUGHT: ок\nFINAL: готово",
        ]
    )
    agent = ReActAgent(
        name="Recover",
        role_prompt="r",
        router=_router(client),
        registry=default_registry(),
        max_steps=4,
    )
    answer, trace = await agent.run("test")
    assert answer == "готово"
    assert any(s.kind is StepKind.ERROR for s in trace.steps)


@pytest.mark.asyncio
async def test_on_step_callback_receives_all_steps() -> None:
    client = _ScriptedClient(["FINAL: hi"])
    agent = ReActAgent(
        name="Cb",
        role_prompt="r",
        router=_router(client),
        registry=default_registry(),
    )
    received = []

    async def cb(step):
        received.append(step.kind)

    await agent.run("ping", on_step=cb)
    assert StepKind.AGENT_START in received
    assert StepKind.FINAL in received
    assert StepKind.AGENT_END in received
