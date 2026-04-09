"""Tool registry для function-calling агентов.

Мини-замена langchain-tools: декоратор `@tool` регистрирует async-функцию
в глобальном `default_registry()`, автоматически выводя JSON-схему
параметров из аннотаций (поддерживаются str/int/float/bool).
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

JSON = dict[str, Any]
ToolFunc = Callable[..., Awaitable[Any]]

_PY_TO_JSON = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
}


def _build_schema(func: ToolFunc) -> JSON:
    sig = inspect.signature(func)
    properties: JSON = {}
    required: list[str] = []
    for name, param in sig.parameters.items():
        # Параметры с _ в начале — внутренние, не показываем LLM
        if name.startswith("_"):
            continue
        annot = param.annotation if param.annotation is not inspect._empty else str
        json_type = _PY_TO_JSON.get(annot, "string")
        properties[name] = {"type": json_type}
        if param.default is inspect._empty:
            required.append(name)
    return {"type": "object", "properties": properties, "required": required}


@dataclass(slots=True)
class Tool:
    name: str
    description: str
    func: ToolFunc
    parameters: JSON

    def to_anthropic(self) -> JSON:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameters,
        }

    def to_openai(self) -> JSON:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass(slots=True)
class ToolRegistry:
    tools: dict[str, Tool] = field(default_factory=dict)

    def register(self, tool: Tool) -> None:
        self.tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        if name not in self.tools:
            raise KeyError(f"unknown tool: {name}")
        return self.tools[name]

    async def call(self, name: str, **kwargs: Any) -> Any:
        return await self.get(name).func(**kwargs)

    def to_anthropic(self) -> list[JSON]:
        return [t.to_anthropic() for t in self.tools.values()]

    def to_openai(self) -> list[JSON]:
        return [t.to_openai() for t in self.tools.values()]

    def __len__(self) -> int:
        return len(self.tools)

    def __contains__(self, name: object) -> bool:
        return name in self.tools


_default = ToolRegistry()


def default_registry() -> ToolRegistry:
    return _default


def tool(
    name: str | None = None,
    description: str | None = None,
    *,
    registry: ToolRegistry | None = None,
) -> Callable[[ToolFunc], ToolFunc]:
    """Декоратор: регистрирует async-функцию как tool."""

    def decorator(func: ToolFunc) -> ToolFunc:
        if not inspect.iscoroutinefunction(func):
            raise TypeError(f"@tool requires async def: {func.__name__}")
        reg = registry or _default
        reg.register(
            Tool(
                name=name or func.__name__,
                description=description or (func.__doc__ or "").strip().splitlines()[0]
                if func.__doc__
                else "",
                func=func,
                parameters=_build_schema(func),
            )
        )
        return func

    return decorator
