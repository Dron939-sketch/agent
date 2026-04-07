"""Chat-роуты: история и отправка сообщения через LLM."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthenticatedUser
from app.db import ConversationRepository
from app.services import default_llm

from .deps import get_current_user, get_session

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatResponse(BaseModel):
    reply: str


@router.get("/history", response_model=list[ChatMessage])
async def history(
    limit: int = 50,
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[ChatMessage]:
    rows = await ConversationRepository(session).history(user.user_id, limit=limit)
    return [ChatMessage(role=r["role"], content=r["content"]) for r in rows]


@router.post("/", response_model=ChatResponse)
async def send(
    body: ChatRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ChatResponse:
    convos = ConversationRepository(session)
    await convos.add(user.user_id, "user", body.message)

    history = await convos.history(user.user_id, limit=20)
    messages = [
        {"role": "system", "content": "Ты Фреди, дружелюбный AI-помощник. Отвечай по-русски."},
        *[{"role": m["role"], "content": m["content"]} for m in history],
    ]
    reply = await default_llm().chat(messages)

    await convos.add(user.user_id, "assistant", reply)
    return ChatResponse(reply=reply)
