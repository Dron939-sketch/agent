"""REST endpoints для напоминаний и задач.

Sprint 8: CRUD + snooze для напоминаний.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field

from app.auth import AuthenticatedUser
from app.core.logging import get_logger
from app.services.tasks import ReminderManager, get_reminder_manager

from .deps import get_current_user

logger = get_logger(__name__)

router = APIRouter(prefix="/api/reminders", tags=["reminders"])


class ReminderCreate(BaseModel):
    text: str = Field(min_length=2, max_length=1000, description="Текст в свободной форме: 'через 2 часа позвонить маме'")
    tz_offset: int = Field(default=3, ge=-12, le=14, description="Часовой пояс (часов от UTC)")


class ReminderDirectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    scheduled_at: str = Field(description="ISO-8601 datetime (UTC)")
    recurrence: str | None = Field(default=None, pattern="^(daily|weekly|monthly)$")


class ReminderSnooze(BaseModel):
    minutes: int = Field(default=15, ge=1, le=1440)


class ReminderResponse(BaseModel):
    id: int | None = None
    task_id: int | None = None
    title: str
    scheduled_at: str | None = None
    recurrence: str | None = None
    created_at: str | None = None


class ReminderListResponse(BaseModel):
    reminders: list[ReminderResponse]
    count: int


@router.post("", response_model=ReminderResponse, status_code=status.HTTP_201_CREATED)
async def create_reminder_nlp(
    body: ReminderCreate,
    user: AuthenticatedUser = Depends(get_current_user),
) -> ReminderResponse:
    """Создаёт напоминание из свободного текста на русском."""
    manager = get_reminder_manager()
    try:
        result = await manager.create_from_text(
            user.user_id,
            body.text,
            tz_offset=body.tz_offset,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    return ReminderResponse(
        task_id=result["task_id"],
        title=result["title"],
        scheduled_at=result["scheduled_at"],
        recurrence=result.get("recurrence"),
    )


@router.post("/direct", response_model=ReminderResponse, status_code=status.HTTP_201_CREATED)
async def create_reminder_direct(
    body: ReminderDirectCreate,
    user: AuthenticatedUser = Depends(get_current_user),
) -> ReminderResponse:
    """Создаёт напоминание с явной датой (для фронтенда)."""
    from datetime import datetime

    manager = get_reminder_manager()
    try:
        scheduled = datetime.fromisoformat(body.scheduled_at)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Invalid datetime: {exc}") from exc

    result = await manager.create(
        user.user_id,
        body.title,
        scheduled_at=scheduled,
        recurrence=body.recurrence,
    )
    return ReminderResponse(
        task_id=result["task_id"],
        title=result["title"],
        scheduled_at=result["scheduled_at"],
        recurrence=result.get("recurrence"),
    )


@router.get("", response_model=ReminderListResponse)
async def list_reminders(
    user: AuthenticatedUser = Depends(get_current_user),
) -> ReminderListResponse:
    """Список активных напоминаний пользователя."""
    manager = get_reminder_manager()
    reminders = await manager.list_pending(user.user_id)
    return ReminderListResponse(
        reminders=[
            ReminderResponse(
                id=r["id"],
                title=r["title"],
                scheduled_at=r["scheduled_at"],
                recurrence=r.get("recurrence"),
                created_at=r.get("created_at"),
            )
            for r in reminders
        ],
        count=len(reminders),
    )


@router.post("/{task_id}/snooze", response_model=dict)
async def snooze_reminder(
    task_id: int,
    body: ReminderSnooze,
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict:
    """Откладывает напоминание на N минут."""
    manager = get_reminder_manager()
    result = await manager.snooze(task_id, user.user_id, minutes=body.minutes)
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Reminder not found")
    return result


@router.delete(
    "/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def cancel_reminder(
    task_id: int,
    user: AuthenticatedUser = Depends(get_current_user),
) -> Response:
    """Отменяет напоминание."""
    manager = get_reminder_manager()
    ok = await manager.cancel(task_id, user.user_id)
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Reminder not found or already done")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
