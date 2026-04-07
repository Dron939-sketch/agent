"""Sequential pipeline: Planner → Researcher → Coder → Critic → Executor.

Каждый агент получает на вход исходную задачу + результаты всех предыдущих
агентов, оформленные как контекст. Все шаги пишутся в общий `Trace`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.services.llm import LLMRouter
from app.services.tools import ToolRegistry, default_registry

from . import roles
from .react import OnStep, ReActAgent
from .trace import Trace


@dataclass(slots=True)
class Pipeline:
    router: LLMRouter
    registry: ToolRegistry = field(default_factory=default_registry)
    profile: str = "smart"
    max_steps_per_agent: int = 6

    def _agent(self, name: str, prompt: str, *, profile: str | None = None) -> ReActAgent:
        return ReActAgent(
            name=name,
            role_prompt=prompt,
            router=self.router,
            registry=self.registry,
            profile=profile or self.profile,
            max_steps=self.max_steps_per_agent,
        )

    async def run(self, task: str, *, on_step: OnStep = None) -> tuple[str, Trace]:
        trace = Trace()
        context: list[tuple[str, str]] = []  # (agent_name, output)

        stages = [
            ("Planner", roles.PLANNER, "fast"),
            ("Researcher", roles.RESEARCHER, self.profile),
            ("Coder", roles.CODER, self.profile),
            ("Critic", roles.CRITIC, "fast"),
            ("Executor", roles.EXECUTOR, self.profile),
        ]

        for name, prompt, profile in stages:
            agent = self._agent(name, prompt, profile=profile)
            ctx = "\n\n".join(f"### {n}\n{out}" for n, out in context)
            sub_task = (
                f"ЗАДАЧА: {task}\n\nКОНТЕКСТ ОТ ПРЕДЫДУЩИХ АГЕНТОВ:\n{ctx or '(пусто)'}"
            )
            output, _ = await agent.run(sub_task, trace=trace, on_step=on_step)
            context.append((name, output))

        final = context[-1][1]
        return final, trace
