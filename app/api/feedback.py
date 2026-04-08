"""Feedback endpoints: лайки/дизлайки на ответы Фреди.

ROUND 2: каждая оценка превращается в урок (lesson) для будущих ответов
через ``feedback_learner.record_lesson`` — BackgroundTask после сохранения.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthenticatedUser
from app.db import FeedbackRepository
from app.services.feedback_learner import record_lesson

from .deps import get_current_user, get_session

router = APIRouter(prefix="/api/feedback", tags=["feedback"])


class FeedbackIn(BaseModel):
    score: int = Field(ge=-1, le=1)  # -1, 0, 1
    message_id: int | None = None
    note: str | None = None


class FeedbackOut(BaseModel):
    id: int
    status: str = "ok"


class StatsOut(BaseModel):
    likes: int
    dislikes: int
    total: int


@router.post("/", response_model=FeedbackOut, status_code=status.HTTP_201_CREATED)
async def submit(
    body: FeedbackIn,
    background: BackgroundTasks,
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> FeedbackOut:
    fb_id = await FeedbackRepository(session).add(
        user_id=user.user_id,
        score=body.score,
        message_id=body.message_id,
        note=body.note,
    )
    # ROUND 2: превращаем feedback в урок для будущих ответов
    if body.score != 0:
        background.add_task(
            record_lesson,
            user_id=user.user_id,
            message_id=body.message_id,
            score=body.score,
            note=body.note,
        )
    return FeedbackOut(id=fb_id)


@router.get("/stats", response_model=StatsOut)
async def stats(
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> StatsOut:
    s = await FeedbackRepository(session).stats(user.user_id)
    return StatsOut(**s)
