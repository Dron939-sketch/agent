"""Тесты Plugin SDK."""

from __future__ import annotations

import pytest

from app.plugins import load_plugins
from app.services.tools import default_registry


@pytest.mark.asyncio
async def test_example_plugin_registers_motivation() -> None:
    loaded = load_plugins()
    assert "example_motivation" in loaded
    reg = default_registry()
    assert "motivation" in reg
    out = await reg.call("motivation")
    assert isinstance(out, str)
    assert len(out) > 0
