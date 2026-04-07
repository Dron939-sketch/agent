"""Auth-роуты: register, login, refresh, me.

PR autonomy:
- email теперь опциональный (мы не отправляем письма) — снимает 422 на
  кривом email при регистрации.
- password min_length=6 (8 был слишком строг для UX).
- username min_length=2 — чтобы короткие никнеймы тоже работали.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthenticatedUser, AuthService

from .deps import get_current_user, get_session

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    email: EmailStr | None = None
    password: str = Field(min_length=6, max_length=128)


class LoginRequest(BaseModel):
    username: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class MeResponse(BaseModel):
    user_id: str
    username: str


@router.post("/register", response_model=MeResponse, status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest, session: AsyncSession = Depends(get_session)
) -> MeResponse:
    auth = AuthService(session)
    user_id = await auth.register(body.username, body.email or "", body.password)
    if user_id is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "username or email already taken")
    return MeResponse(user_id=user_id, username=body.username)


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest, session: AsyncSession = Depends(get_session)
) -> TokenResponse:
    pair = await AuthService(session).login(body.username, body.password)
    if pair is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")
    return TokenResponse(access_token=pair.access, refresh_token=pair.refresh)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    body: RefreshRequest, session: AsyncSession = Depends(get_session)
) -> TokenResponse:
    pair = await AuthService(session).refresh(body.refresh_token)
    if pair is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid refresh token")
    return TokenResponse(access_token=pair.access, refresh_token=pair.refresh)


@router.get("/me", response_model=MeResponse)
async def me(user: AuthenticatedUser = Depends(get_current_user)) -> MeResponse:
    return MeResponse(user_id=user.user_id, username=user.username)
