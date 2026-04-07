"""JWT access/refresh токены на чистом hmac+base64 (без внешних зависимостей).

Можно безболезненно заменить на PyJWT в следующем PR — здесь специально
без новой зависимости, чтобы CI оставался лёгким.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any

from app.core.config import Config

ALGORITHM = "HS256"
ACCESS_TTL_SECONDS = 60 * 60          # 1 час
REFRESH_TTL_SECONDS = 60 * 60 * 24 * 7  # 7 дней


class TokenError(Exception):
    """Ошибка валидации/декодирования токена."""


@dataclass(slots=True)
class TokenPair:
    access: str
    refresh: str


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    pad = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)


def _sign(message: bytes) -> bytes:
    secret = Config.SECRET_KEY.encode("utf-8")
    return hmac.new(secret, message, hashlib.sha256).digest()


def encode(payload: dict[str, Any]) -> str:
    header = {"alg": ALGORITHM, "typ": "JWT"}
    h = _b64url_encode(json.dumps(header, separators=(",", ":")).encode())
    p = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = f"{h}.{p}".encode()
    sig = _b64url_encode(_sign(signing_input))
    return f"{h}.{p}.{sig}"


def decode(token: str) -> dict[str, Any]:
    try:
        h, p, s = token.split(".")
    except ValueError as exc:
        raise TokenError("malformed token") from exc

    expected = _b64url_encode(_sign(f"{h}.{p}".encode()))
    if not hmac.compare_digest(expected, s):
        raise TokenError("bad signature")

    payload = json.loads(_b64url_decode(p))
    if int(payload.get("exp", 0)) < int(time.time()):
        raise TokenError("expired")
    return payload


def create_pair(user_id: str) -> TokenPair:
    now = int(time.time())
    access = encode({"sub": user_id, "type": "access", "iat": now, "exp": now + ACCESS_TTL_SECONDS})
    refresh = encode({"sub": user_id, "type": "refresh", "iat": now, "exp": now + REFRESH_TTL_SECONDS})
    return TokenPair(access=access, refresh=refresh)


def verify_access(token: str) -> str:
    """Возвращает user_id из валидного access-токена."""
    payload = decode(token)
    if payload.get("type") != "access":
        raise TokenError("not an access token")
    sub = payload.get("sub")
    if not isinstance(sub, str):
        raise TokenError("missing sub")
    return sub


def verify_refresh(token: str) -> str:
    payload = decode(token)
    if payload.get("type") != "refresh":
        raise TokenError("not a refresh token")
    sub = payload.get("sub")
    if not isinstance(sub, str):
        raise TokenError("missing sub")
    return sub
