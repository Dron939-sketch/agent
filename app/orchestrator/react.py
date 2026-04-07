"""ReAct-агент: provider-agnostic tool-use цикл.

Протокол ответа модели:

    THOUGHT: <свободные размышления>
    ACTION: <tool_name>
    ARGS: {"key": "value"}

    или (когда готов финальный ответ):

    THOUGHT: ...
    FINAL: <ответ пользователю>

Агент парсит вывод, вызывает tool, кладёт OBSERVATION обратно в историю
и повторяет до FINAL или достижения `max_steps`.
"""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.core.logging import get_logger
from app.services.llm import ChatMessage, LLMRouter
from app.services.tools import ToolRegistry, default_registry

from .trace import Step, StepKind, Trace

logger = get_logger(__name__)

OnStep = Callable[[Step], Awaitable[None]] | None

_ACTION_RE = re.compile(r"ACTION:\s*([a-zA-Z_][\w]*)", re.IGNORECASE)
_ARGS_RE = re.compile(r"ARGS:\s*(\{.*?\})", re.IGNORECASE | re.DOTALL)
_FINAL_RE = re.compile(r"FINAL:\s*(.+)$", re.IGNORECASE | re.DOTALL)
_THOUGHT_RE = re.compile(r"THOUGHT:\s*(.+?)(?=\n[A-Z]+:|\Z)", re.IGNORECASE | re.DOTALL)


def _format_tools(registry: ToolRegistry) -> str:
    if not len(registry):
        return "(нет инструментов)"
    lines = []
    for tool in registry.tools.values():
        params = ", ".join(tool.parameters.get("properties", {}).keys())
        lines.append(f"- {tool.name}({params}): {tool.description}")
    return "\n".join(lines)


def _build_system_prompt(role_prompt: str, registry: ToolRegistry) -> str:
    return f"""{role_prompt}

У тебя есть инструменты:
{_format_tools(registry)}

ФОРМАТ ОТВЕТА (строго):
- если нужно вызвать инструмент:
THOUGHT: <твои рассуждения>
ACTION: <имя инструмента>
ARGS: {{"arg": "value"}}

- если ответ готов:
THOUGHT: <итоговое рассуждение>
FINAL: <ответ пользователю>

Никакого текста вне этих блоков. JSON в ARGS — валидный."""


@dataclass(slots=True)
class ReActAgent:
    name: str
    role_prompt: str
    router: LLMRouter
    registry: ToolRegistry
    profile: str = "smart"
    max_steps: int = 6

    async def run(
        self,
        task: str,
        *,
        trace: Trace | None = None,
        on_step: OnStep = None,
    ) -> tuple[str, Trace]:
        trace = trace or Trace()
        await _emit(on_step, trace.add(Step(StepKind.AGENT_START, self.name, task)))

        history: list[ChatMessage] = [
            ChatMessage(role="system", content=_build_system_prompt(self.role_prompt, self.registry)),
            ChatMessage(role="user", content=task),
        ]

        for step_idx in range(self.max_steps):
            try:
                resp = await self.router.chat(history, profile=self.profile)  # type: ignore[arg-type]
            except Exception as exc:
                err = trace.add(Step(StepKind.ERROR, self.name, f"LLM error: {exc}"))
                await _emit(on_step, err)
                break

            text = resp.text.strip()
            history.append(ChatMessage(role="assistant", content=text))

            thought = _THOUGHT_RE.search(text)
            if thought:
                await _emit(on_step, trace.add(Step(StepKind.THOUGHT, self.name, thought.group(1).strip())))

            final_match = _FINAL_RE.search(text)
            if final_match:
                answer = final_match.group(1).strip()
                await _emit(on_step, trace.add(Step(StepKind.FINAL, self.name, answer)))
                await _emit(on_step, trace.add(Step(StepKind.AGENT_END, self.name, answer)))
                return answer, trace

            action_match = _ACTION_RE.search(text)
            args_match = _ARGS_RE.search(text)
            if not action_match:
                obs = "Не распознан ACTION или FINAL. Используй формат строго."
                history.append(ChatMessage(role="user", content=f"OBSERVATION: {obs}"))
                await _emit(on_step, trace.add(Step(StepKind.ERROR, self.name, obs)))
                continue

            tool_name = action_match.group(1)
            try:
                args = json.loads(args_match.group(1)) if args_match else {}
            except json.JSONDecodeError as exc:
                obs = f"ARGS не JSON: {exc}"
                history.append(ChatMessage(role="user", content=f"OBSERVATION: {obs}"))
                await _emit(on_step, trace.add(Step(StepKind.ERROR, self.name, obs)))
                continue

            await _emit(
                on_step,
                trace.add(Step(StepKind.ACTION, self.name, content=tool_name, tool=tool_name, args=args)),
            )

            try:
                observation = await self.registry.call(tool_name, **args)
            except Exception as exc:
                observation = f"tool error: {exc}"

            obs_text = str(observation)[:2000]
            history.append(ChatMessage(role="user", content=f"OBSERVATION: {obs_text}"))
            await _emit(on_step, trace.add(Step(StepKind.OBSERVATION, self.name, obs_text, tool=tool_name)))

        # Достигли max_steps без FINAL
        msg = f"max_steps={self.max_steps} reached without FINAL"
        await _emit(on_step, trace.add(Step(StepKind.ERROR, self.name, msg)))
        await _emit(on_step, trace.add(Step(StepKind.AGENT_END, self.name, msg)))
        return msg, trace


async def _emit(callback: OnStep, step: Step) -> None:
    if callback is not None:
        await callback(step)


def make_default_agent(
    name: str,
    role_prompt: str,
    *,
    router: LLMRouter | None = None,
    registry: ToolRegistry | None = None,
    profile: str = "smart",
    max_steps: int = 6,
) -> ReActAgent:
    from app.services.llm import default_router

    return ReActAgent(
        name=name,
        role_prompt=role_prompt,
        router=router or default_router(),
        registry=registry or default_registry(),
        profile=profile,
        max_steps=max_steps,
    )
