"""Тесты LLM-роутера и tools registry."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret")

from app.services.llm import (  # noqa: E402
    ChatMessage,
    ChatResponse,
    LLMError,
    LLMRouter,
    Usage,
)
from app.services.tools import default_registry  # noqa: E402  # noqa: F401 - регистрация
from app.services.tools import builtin  # noqa: E402, F401


class _FailClient:
    name = "fail"
    model = "fail-1"

    async def chat(self, messages, *, temperature=0.7, max_tokens=2000):
        raise LLMError("boom")

    async def stream(self, messages, *, temperature=0.7, max_tokens=2000) -> AsyncIterator[str]:
        if False:
            yield ""
        raise LLMError("boom")


class _OkClient:
    name = "ok"
    model = "ok-1"

    async def chat(self, messages, *, temperature=0.7, max_tokens=2000):
        return ChatResponse(text="hello", model=self.model, usage=Usage())

    async def stream(self, messages, *, temperature=0.7, max_tokens=2000) -> AsyncIterator[str]:
        for token in ("he", "llo"):
            yield token


@pytest.mark.asyncio
async def test_router_fallback_to_next_provider() -> None:
    router = LLMRouter(profiles={"smart": [_FailClient(), _OkClient()]})
    resp = await router.chat([ChatMessage(role="user", content="hi")], profile="smart")
    assert resp.text == "hello"
    assert resp.model == "ok-1"


@pytest.mark.asyncio
async def test_router_all_fail_raises() -> None:
    router = LLMRouter(profiles={"smart": [_FailClient(), _FailClient()]})
    with pytest.raises(LLMError):
        await router.chat([ChatMessage(role="user", content="hi")], profile="smart")


@pytest.mark.asyncio
async def test_router_stream_fallback() -> None:
    router = LLMRouter(profiles={"smart": [_FailClient(), _OkClient()]})
    chunks: list[str] = []
    async for c in router.stream([ChatMessage(role="user", content="hi")], profile="smart"):
        chunks.append(c)
    assert "".join(chunks) == "hello"


@pytest.mark.asyncio
async def test_calculator_tool() -> None:
    reg = default_registry()
    assert "calculator" in reg
    out = await reg.call("calculator", expression="2 + 3 * 4")
    assert out == "14"


@pytest.mark.asyncio
async def test_now_tool_returns_iso() -> None:
    reg = default_registry()
    out = await reg.call("now")
    assert "T" in out and out.endswith("+00:00")


def test_registry_anthropic_schema_has_tools() -> None:
    reg = default_registry()
    schemas = reg.to_anthropic()
    names = {s["name"] for s in schemas}
    assert {"calculator", "now", "fetch_url", "web_search"}.issubset(names)
    calc = next(s for s in schemas if s["name"] == "calculator")
    assert calc["input_schema"]["properties"]["expression"]["type"] == "string"
    assert "expression" in calc["input_schema"]["required"]
