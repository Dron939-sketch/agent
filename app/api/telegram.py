"""Telegram linking: привязка Telegram аккаунта к Фреди-пользователю.

Flow:
1. Фронтенд вызывает POST /api/telegram/link-code → получает 6-значный код
2. Пользователь пишет боту /link <код>
3. Бот вызывает POST /api/telegram/confirm → привязка chat_id к user_id
4. GET /api/telegram/status → проверка привязки
5. DELETE /api/telegram/unlink → отвязка
"""

from __future__ import annotations

import json
import secrets
import time

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthenticatedUser
from app.db import UserRepository
from app.db.session import get_sessionmaker

from .deps import get_current_user

router = APIRouter(prefix="/api/telegram", tags=["telegram"])

# In-memory хранилище кодов привязки: code → {user_id, expires}
_pending_codes: dict[str, dict] = {}


class LinkCodeResponse(BaseModel):
    code: str
    bot_username: str
    expires_in: int


class ConfirmRequest(BaseModel):
    code: str
    chat_id: int


class StatusResponse(BaseModel):
    linked: bool
    chat_id: int | None = None


def _get_bot_username() -> str:
    import os
    return os.environ.get("TELEGRAM_BOT_USERNAME", "freddy_ai_bot")


@router.post("/link-code", response_model=LinkCodeResponse)
async def generate_link_code(
    user: AuthenticatedUser = Depends(get_current_user),
) -> LinkCodeResponse:
    """Генерирует 6-значный код для привязки Telegram."""
    # Удаляем старые коды этого пользователя
    expired = [k for k, v in _pending_codes.items() if v["expires"] < time.time() or v["user_id"] == user.user_id]
    for k in expired:
        _pending_codes.pop(k, None)

    code = secrets.token_hex(3).upper()[:6]  # 6-символьный hex
    _pending_codes[code] = {"user_id": user.user_id, "expires": time.time() + 300}  # 5 минут

    return LinkCodeResponse(code=code, bot_username=_get_bot_username(), expires_in=300)


@router.post("/confirm")
async def confirm_link(body: ConfirmRequest) -> dict:
    """Вызывается ботом: привязывает chat_id к user_id по коду."""
    pending = _pending_codes.pop(body.code.upper(), None)
    if not pending or pending["expires"] < time.time():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Код недействителен или истёк")

    user_id = pending["user_id"]

    sm = get_sessionmaker()
    async with sm() as session:
        repo = UserRepository(session)
        user = await repo.get(user_id)
        if not user:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Пользователь не найден")

        # Сохраняем chat_id в settings
        settings = json.loads(user.settings or "{}")
        settings["telegram_chat_id"] = body.chat_id
        await repo.update_settings(user_id, settings)
        await session.commit()

    return {"ok": True, "user_id": user_id, "chat_id": body.chat_id}


@router.get("/status", response_model=StatusResponse)
async def telegram_status(
    user: AuthenticatedUser = Depends(get_current_user),
) -> StatusResponse:
    """Проверяет привязан ли Telegram."""
    sm = get_sessionmaker()
    async with sm() as session:
        repo = UserRepository(session)
        u = await repo.get(user.user_id)
        if not u:
            return StatusResponse(linked=False)
        settings = json.loads(u.settings or "{}")
        chat_id = settings.get("telegram_chat_id")
        return StatusResponse(linked=bool(chat_id), chat_id=chat_id)


@router.delete("/unlink")
async def unlink_telegram(
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict:
    """Отвязывает Telegram."""
    sm = get_sessionmaker()
    async with sm() as session:
        repo = UserRepository(session)
        u = await repo.get(user.user_id)
        if u:
            settings = json.loads(u.settings or "{}")
            settings.pop("telegram_chat_id", None)
            await repo.update_settings(user.user_id, settings)
            await session.commit()
    return {"ok": True}


# Хелпер для бота: получить user_id по chat_id
async def get_user_id_by_chat_id(chat_id: int) -> str | None:
    """Ищет user_id по telegram_chat_id в БД."""
    from sqlalchemy import select, text as sql_text
    from app.db.models import User

    sm = get_sessionmaker()
    async with sm() as session:
        # PostgreSQL JSON поиск
        result = await session.execute(
            select(User.user_id).where(
                User.settings.contains(f'"telegram_chat_id": {chat_id}')
            )
        )
        row = result.scalar_one_or_none()
        if row:
            return row

        # Fallback: пробуем точное совпадение через LIKE
        result = await session.execute(
            select(User.user_id).where(
                User.settings.like(f'%"telegram_chat_id": {chat_id}%')
            )
        )
        return result.scalar_one_or_none()
