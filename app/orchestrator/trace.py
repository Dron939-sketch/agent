"""Трассировка работы агентов: Step/Trace + JSON-сериализация."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class StepKind(str, Enum):
    THOUGHT = "thought"
    ACTION = "action"
    OBSERVATION = "observation"
    FINAL = "final"
    ERROR = "error"
    AGENT_START = "agent_start"
    AGENT_END = "agent_end"


@dataclass(slots=True)
class Step:
    kind: StepKind
    agent: str
    content: str = ""
    tool: str | None = None
    args: dict[str, Any] | None = None
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["kind"] = self.kind.value
        return d


@dataclass(slots=True)
class Trace:
    """Накопитель шагов одного запуска агента/пайплайна."""

    steps: list[Step] = field(default_factory=list)

    def add(self, step: Step) -> Step:
        self.steps.append(step)
        return step

    def final(self) -> str | None:
        for s in reversed(self.steps):
            if s.kind is StepKind.FINAL:
                return s.content
        return None

    def to_list(self) -> list[dict[str, Any]]:
        return [s.to_dict() for s in self.steps]
