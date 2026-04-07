"""Web Push endpoints: VAPID-конфиг, подписка, тестовая отправка."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import delete, select

from app.auth import AuthenticatedUser
from app.core.config import Config
from app.db import session_scope
from app.db.models import PushSubscription
from app.services.push import WebPushService

from .deps import get_current_user

router = APIRouter(prefix="/api/push", tags=["push"])


class SubscriptionIn(BaseModel):
    endpoint: str
    keys: dict[str, str]


class TestPushIn(BaseModel):
    title: str = "Фреди"
    body: str = "Тестовое уведомление"


@router.get("/public-key")
async def public_key() -> dict[str, str]:
    return {"key": Config.VAPID_PUBLIC_KEY}


@router.post("/subscribe", status_code=status.HTTP_201_CREATED)
async def subscribe(
    body: SubscriptionIn,
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, str]:
    payload = json.dumps({"endpoint": body.endpoint, "keys": body.keys})
    async with session_scope() as session:
        # дедуп: одна и та же endpoint = один ряд
        await session.execute(
            delete(PushSubscription).where(
                PushSubscription.user_id == user.user_id,
                PushSubscription.endpoint == body.endpoint,
            )
        )
        session.add(
            PushSubscription(
                user_id=user.user_id, endpoint=body.endpoint, payload=payload
            )
        )
    return {"status": "ok"}


@router.post("/test")
async def test_push(
    body: TestPushIn,
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    service = WebPushService()
    if not service.is_configured():
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "VAPID keys are not configured",
        )
    sent = 0
    async with session_scope() as session:
        result = await session.execute(
            select(PushSubscription).where(PushSubscription.user_id == user.user_id)
        )
        subs = list(result.scalars().all())
    for sub in subs:
        try:
            data = json.loads(sub.payload)
        except Exception:
            continue
        ok = await service.send(
            data,
            {"title": body.title, "body": body.body, "icon": "/icon-192.png"},
        )
        if ok:
            sent += 1
    return {"sent": sent, "total": len(subs)}
