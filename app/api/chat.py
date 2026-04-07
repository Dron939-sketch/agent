"""Chat-роуты: история, отправка, SSE-стриминг через LLMRouter."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthenticatedUser
from app.db import ConversationRepository
from app.services import ChatMessage, default_router

from .deps import get_current_user, get_session

router = APIRouter(prefix="/api/chat", tags=["chat"])

SYSTEM_PROMPT = "Ты Фреди, дружелюбный AI-помощник. Отвечай по-русски."


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    profile: str = Field(default="smart")


class ChatMessageOut(BaseModel):
    role: str
    content: str


class ChatResponseOut(BaseModel):
    reply: str
    model: str


def _build_history(rows: list[dict]) -> list[ChatMessage]:
    return [ChatMessage(role="system", content=SYSTEM_PROMPT)] + [
        ChatMessage(role=r["role"], content=r["content"]) for r in rows  # type: ignore[arg-type]
    ]


@router.get("/history", response_model=list[ChatMessageOut])
async def history(
    limit: int = 50,
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[ChatMessageOut]:
    rows = await ConversationRepository(session).history(user.user_id, limit=limit)
    return [ChatMessageOut(role=r["role"], content=r["content"]) for r in rows]


@router.post("/", response_model=ChatResponseOut)
async def send(
    body: ChatRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ChatResponseOut:
    convos = ConversationRepository(session)
    await convos.add(user.user_id, "user", body.message)

    rows = await convos.history(user.user_id, limit=20)
    messages = _build_history(rows)
    response = await default_router().chat(messages, profile=body.profile)  # type: ignore[arg-type]

    await convos.add(user.user_id, "assistant", response.text)
    return ChatResponseOut(reply=response.text, model=response.model)


@router.post("/stream")
async def stream(
    body: ChatRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    """Server-Sent Events: токены от первого живого провайдера в цепочке."""
    convos = ConversationRepository(session)
    await convos.add(user.user_id, "user", body.message)
    rows = await convos.history(user.user_id, limit=20)
    messages = _build_history(rows)

    async def event_source() -> AsyncIterator[bytes]:
        collected: list[str] = []
        try:
            async for chunk in default_router().stream(messages, profile=body.profile):  # type: ignore[arg-type]
                collected.append(chunk)
                yield f"data: {chunk}\n\n".encode()
            yield b"event: done\ndata: end\n\n"
        finally:
            full = "".join(collected)
            if full:
                async with session.begin_nested():
                    await ConversationRepository(session).add(
                        user.user_id, "assistant", full
                    )
                await session.commit()

    return StreamingResponse(event_source(), media_type="text/event-stream")
