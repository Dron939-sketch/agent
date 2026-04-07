"""Сервис аутентификации поверх async-репозиториев и argon2/JWT.

Заменяет legacy `AuthManager` из main.py.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.db import SessionRepository, UserRepository

from . import passwords, tokens
from .tokens import TokenError, TokenPair


@dataclass(slots=True)
class AuthenticatedUser:
    user_id: str
    username: str


class AuthService:
    """Высокоуровневые операции: register / login / refresh / verify."""

    def __init__(self, session: AsyncSession) -> None:
        self.users = UserRepository(session)
        self.sessions = SessionRepository(session)

    async def register(self, username: str, email: str, password: str) -> Optional[str]:
        user_id = secrets.token_hex(16)
        ok = await self.users.create(
            user_id=user_id,
            username=username,
            email=email,
            password_hash=passwords.hash_password(password),
        )
        return user_id if ok else None

    async def login(self, username: str, password: str) -> Optional[TokenPair]:
        user = await self.users.get_by_username(username)
        if user is None or not user.password_hash:
            return None
        if not passwords.verify_password(password, user.password_hash):
            return None
        return tokens.create_pair(user.user_id)

    async def refresh(self, refresh_token: str) -> Optional[TokenPair]:
        try:
            user_id = tokens.verify_refresh(refresh_token)
        except TokenError:
            return None
        user = await self.users.get(user_id)
        if user is None:
            return None
        return tokens.create_pair(user_id)

    async def verify(self, access_token: str) -> Optional[AuthenticatedUser]:
        try:
            user_id = tokens.verify_access(access_token)
        except TokenError:
            return None
        user = await self.users.get(user_id)
        if user is None or not user.username:
            return None
        return AuthenticatedUser(user_id=user.user_id, username=user.username)
