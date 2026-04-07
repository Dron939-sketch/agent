"""Endpoints for multi-agent runs: REST + WebSocket live trace."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from app.auth import AuthenticatedUser
from app.orchestrator import Pipeline, ReActAgent, Step
from app.services.llm import default_router
from app.services.tools import default_registry

from .deps import get_current_user

router = APIRouter(prefix="/api/agents", tags=["agents"])


class RunRequest(BaseModel):
    task: str = Field(min_length=1, max_length=4000)
    profile: str = "smart"
    mode: str = Field(default="single", pattern="^(single|pipeline)$")


class RunResponse(BaseModel):
    answer: str
    trace: list[dict]


@router.post("/run", response_model=RunResponse)
async def run(
    body: RunRequest,
    _user: AuthenticatedUser = Depends(get_current_user),
) -> RunResponse:
    """Синхронный запуск (single ReAct либо полный pipeline)."""
    if body.mode == "pipeline":
        pipeline = Pipeline(router=default_router(), registry=default_registry(), profile=body.profile)
        answer, trace = await pipeline.run(body.task)
    else:
        agent = ReActAgent(
            name="Freddy",
            role_prompt="Ты Фреди, всемогущий AI-помощник. Решай задачи пользователя, используя tools.",
            router=default_router(),
            registry=default_registry(),
            profile=body.profile,
        )
        answer, trace = await agent.run(body.task)
    return RunResponse(answer=answer, trace=trace.to_list())


@router.websocket("/ws")
async def ws_run(websocket: WebSocket) -> None:
    """WebSocket: клиент шлёт {task, profile, mode}, получает поток шагов."""
    await websocket.accept()
    try:
        payload = await websocket.receive_json()
    except Exception:
        await websocket.close(code=1003)
        return

    task = payload.get("task")
    if not isinstance(task, str) or not task:
        await websocket.send_json({"error": "missing task"})
        await websocket.close(code=1003)
        return

    profile = payload.get("profile", "smart")
    mode = payload.get("mode", "single")

    queue: asyncio.Queue[Step | None] = asyncio.Queue()

    async def on_step(step: Step) -> None:
        await queue.put(step)

    async def runner() -> str:
        if mode == "pipeline":
            pipeline = Pipeline(router=default_router(), registry=default_registry(), profile=profile)
            answer, _ = await pipeline.run(task, on_step=on_step)
        else:
            agent = ReActAgent(
                name="Freddy",
                role_prompt="Ты Фреди, всемогущий AI-помощник.",
                router=default_router(),
                registry=default_registry(),
                profile=profile,
            )
            answer, _ = await agent.run(task, on_step=on_step)
        await queue.put(None)
        return answer

    runner_task = asyncio.create_task(runner())
    try:
        while True:
            item = await queue.get()
            if item is None:
                break
            await websocket.send_json({"type": "step", "step": item.to_dict()})
        answer = await runner_task
        await websocket.send_json({"type": "done", "answer": answer})
    except WebSocketDisconnect:
        runner_task.cancel()
    finally:
        if not runner_task.done():
            runner_task.cancel()
        try:
            await websocket.close()
        except Exception:
            pass
