"""API для проактивных триггеров + WebSocket для real-time уведомлений.

Sprint 6: WebSocket канал для пуш-уведомлений в VoiceWakeMode.
"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect

from app.auth import AuthenticatedUser
from app.core.logging import get_logger
from app.services.triggers import TriggerResult, get_trigger_engine

from .deps import get_current_user

logger = get_logger(__name__)

router = APIRouter(prefix="/api/triggers", tags=["triggers"])


@router.get("/check")
async def check_triggers(
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict:
    """Принудительная проверка триггеров для текущего пользователя."""
    engine = get_trigger_engine()
    results = await engine.force_evaluate(user.user_id)
    return {
        "triggers": [
            {
                "source": r.source,
                "message": r.message,
                "title": r.title,
                "priority": r.priority.name,
                "data": r.data,
            }
            for r in results
        ],
        "count": len(results),
    }


@router.websocket("/ws")
async def trigger_ws(
    ws: WebSocket,
    token: str = Query(...),
) -> None:
    """WebSocket для real-time получения проактивных уведомлений.

    Фронтенд подключается с ?token=JWT и получает JSON-события
    когда срабатывают триггеры для данного пользователя.
    """
    # Верифицируем токен
    from app.auth import AuthService

    auth = AuthService()
    user = await auth.verify(token)
    if not user:
        await ws.close(code=4001, reason="unauthorized")
        return

    await ws.accept()
    engine = get_trigger_engine()
    queue: asyncio.Queue[TriggerResult] = asyncio.Queue(maxsize=50)
    engine.subscribe_ws(user.user_id, queue)

    try:
        # Отправляем текущие триггеры при подключении
        current = await engine.force_evaluate(user.user_id)
        for r in current:
            await ws.send_json(_result_to_json(r))

        # Слушаем новые триггеры + ping от клиента
        while True:
            try:
                result = await asyncio.wait_for(queue.get(), timeout=30)
                await ws.send_json(_result_to_json(result))
            except asyncio.TimeoutError:
                # Heartbeat
                await ws.send_json({"type": "ping"})
            except WebSocketDisconnect:
                break

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.debug("Trigger WS error: %s", exc)
    finally:
        engine.unsubscribe_ws(user.user_id, queue)
        try:
            await ws.close()
        except Exception:
            pass


def _result_to_json(r: TriggerResult) -> dict:
    return {
        "type": "trigger",
        "source": r.source,
        "message": r.message,
        "title": r.title,
        "priority": r.priority.name,
        "data": r.data,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }
