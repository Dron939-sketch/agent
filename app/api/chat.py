"""Chat-роуты с памятью: recall + Varitype-профиль + LLMRouter + SSE."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthenticatedUser
from app.db import ConversationRepository, UserRepository
from app.services import ChatMessage, default_router
from app.services.memory import MemoryRecord, default_memory
from app.services.profile import build_profile_prompt

from .deps import get_current_user, get_session

router = APIRouter(prefix="/api/chat", tags=["chat"])

BASE_SYSTEM = (
    "Ты Фреди, дружелюбный и всемогущий AI-помощник. Отвечай по-русски, "
    "обращайся на «ты», будь полезным и эмпатичным."
)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    profile: str = Field(default="smart")
    use_memory: bool = True


class ChatMessageOut(BaseModel):
    role: str
    content: str


class ChatResponseOut(BaseModel):
    reply: str
    model: str
    recalled: list[str] = Field(default_factory=list)


async def _user_profile_prompt(session: AsyncSession, user_id: str) -> str:
    user = await UserRepository(session).get(user_id)
    if not user or not user.profile:
        return ""
    try:
        profile = json.loads(user.profile)
    except Exception:
        return ""
    return build_profile_prompt(profile)


async def _recall(user_id: str, query: str, top_k: int = 3) -> list[MemoryRecord]:
    try:
        return await default_memory().search(query, user_id=user_id, top_k=top_k)
    except Exception:
        return []


def _build_messages(
    base_history: list[dict],
    user_message: str,
    profile_prompt: str,
    recalled: list[MemoryRecord],
) -> list[ChatMessage]:
    system_parts: list[str] = [BASE_SYSTEM]
    if profile_prompt:
        system_parts.append(profile_prompt)
    if recalled:
        memo = "\n".join(f"- {r.text}" for r in recalled)
        system_parts.append(f"РЕЛЕВАНТНАЯ ПАМЯТЬ:\n{memo}")
    return (
        [ChatMessage(role="system", content="\n\n".join(system_parts))]
        + [ChatMessage(role=m["role"], content=m["content"]) for m in base_history]  # type: ignore[arg-type]
        + [ChatMessage(role="user", content=user_message)]
    )


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
    profile_prompt = await _user_profile_prompt(session, user.user_id)
    recalled = await _recall(user.user_id, body.message) if body.use_memory else []
    messages = _build_messages(rows[:-1], body.message, profile_prompt, recalled)

    response = await default_router().chat(messages, profile=body.profile)  # type: ignore[arg-type]
    await convos.add(user.user_id, "assistant", response.text)

    if body.use_memory:
        try:
            await default_memory().add(
                [
                    MemoryRecord(id="", text=body.message, user_id=user.user_id, metadata={"role": "user"}),
                    MemoryRecord(
                        id="", text=response.text, user_id=user.user_id, metadata={"role": "assistant"}
                    ),
                ]
            )
        except Exception:
            pass

    return ChatResponseOut(
        reply=response.text,
        model=response.model,
        recalled=[r.text for r in recalled],
    )


@router.post("/stream")
async def stream(
    body: ChatRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    convos = ConversationRepository(session)
    await convos.add(user.user_id, "user", body.message)
    rows = await convos.history(user.user_id, limit=20)
    profile_prompt = await _user_profile_prompt(session, user.user_id)
    recalled = await _recall(user.user_id, body.message) if body.use_memory else []
    messages = _build_messages(rows[:-1], body.message, profile_prompt, recalled)

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
                await ConversationRepository(session).add(user.user_id, "assistant", full)
                await session.commit()
                if body.use_memory:
                    try:
                        await default_memory().add(
                            [
                                MemoryRecord(id="", text=body.message, user_id=user.user_id),
                                MemoryRecord(id="", text=full, user_id=user.user_id),
                            ]
                        )
                    except Exception:
                        pass

    return StreamingResponse(event_source(), media_type="text/event-stream")
