"""Хеширование паролей через argon2id."""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    """Возвращает argon2id-хеш."""
    return _hasher.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    """Проверяет пароль; не падает на неверном хеше."""
    try:
        return _hasher.verify(hashed, password)
    except VerifyMismatchError:
        return False
    except Exception:
        return False


def needs_rehash(hashed: str) -> bool:
    """True, если параметры argon2 устарели и стоит перехешировать."""
    try:
        return _hasher.check_needs_rehash(hashed)
    except Exception:
        return True
