"""JWT access/refresh токены на чистом hmac+base64 (без внешних зависимостей)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any

from app.core.config import Config

logger = logging.getLogger(__name__)

ALGORITHM = "HS256"
ACCESS_TTL_SECONDS = 60 * 60 * 24          # 24 часа
REFRESH_TTL_SECONDS = 60 * 60 * 24 * 30   # 30 дней

# Стабильный per-process кеш SECRET_KEY: вычисляется один раз при первом
# использовании, читая ENV (а не Config-snapshot модуля). Это критично для
# мульти-воркерного uvicorn: каждый воркер должен использовать ОДИН и тот же
# секрет, иначе токены становятся невалидными между запросами.
_secret_cache: bytes | None = None


def _secret() -> bytes:
    global _secret_cache
    if _secret_cache is not None:
        return _secret_cache
    raw = os.environ.get("SECRET_KEY") or Config.SECRET_KEY
    if not raw or raw == "change-me":
        logger.warning(
            "⚠️ SECRET_KEY не задан или равен placeholder — токены не будут "
            "переживать рестарты. Установи SECRET_KEY в env."
        )
    _secret_cache = raw.encode("utf-8")
    return _secret_cache


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
    return hmac.new(_secret(), message, hashlib.sha256).digest()


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
    access = encode(
        {"sub": user_id, "type": "access", "iat": now, "exp": now + ACCESS_TTL_SECONDS}
    )
    refresh = encode(
        {"sub": user_id, "type": "refresh", "iat": now, "exp": now + REFRESH_TTL_SECONDS}
    )
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
