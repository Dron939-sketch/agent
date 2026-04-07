"""Authentication: argon2 passwords, JWT access/refresh, AuthService."""

from .passwords import hash_password, needs_rehash, verify_password
from .service import AuthenticatedUser, AuthService
from .tokens import (
    ACCESS_TTL_SECONDS,
    REFRESH_TTL_SECONDS,
    TokenError,
    TokenPair,
    create_pair,
    verify_access,
    verify_refresh,
)

__all__ = [
    "hash_password",
    "verify_password",
    "needs_rehash",
    "AuthService",
    "AuthenticatedUser",
    "TokenPair",
    "TokenError",
    "create_pair",
    "verify_access",
    "verify_refresh",
    "ACCESS_TTL_SECONDS",
    "REFRESH_TTL_SECONDS",
]
