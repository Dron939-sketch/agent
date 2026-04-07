"""Web Push subscriptions: модель + репозиторий + сервис.

Схема таблицы добавляется в `app/db/models.py` (PushSubscription).
Отправка через `pywebpush` (lazy import — опциональная зависимость).
"""

from __future__ import annotations

import json
from typing import Any

from app.core.config import Config
from app.core.logging import get_logger

logger = get_logger(__name__)


class WebPushService:
    """Тонкая обёртка над `pywebpush`."""

    def __init__(self) -> None:
        self.private_key = Config.VAPID_PRIVATE_KEY
        self.subject = Config.VAPID_SUBJECT

    def is_configured(self) -> bool:
        return bool(self.private_key and Config.VAPID_PUBLIC_KEY)

    async def send(self, subscription: dict[str, Any], payload: dict[str, Any]) -> bool:
        """Отправляет уведомление одному подписчику."""
        if not self.is_configured():
            logger.warning("Web push not configured (VAPID keys missing)")
            return False
        try:
            from pywebpush import WebPushException, webpush  # type: ignore
        except ImportError:
            logger.error("pywebpush not installed; `pip install pywebpush`")
            return False

        try:
            webpush(
                subscription_info=subscription,
                data=json.dumps(payload),
                vapid_private_key=self.private_key,
                vapid_claims={"sub": self.subject},
            )
            return True
        except WebPushException as exc:  # pragma: no cover - сетевое
            logger.warning("Web push failed: %s", exc)
            return False
