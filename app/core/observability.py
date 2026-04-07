"""Observability: Sentry init (опционально, без падения если SDK не установлен)."""

from __future__ import annotations

from .config import Config
from .logging import get_logger

logger = get_logger(__name__)

_initialized = False


def init_sentry() -> None:
    """Идемпотентная инициализация Sentry; молча no-op без DSN."""
    global _initialized
    if _initialized or not Config.SENTRY_DSN:
        return
    try:
        import sentry_sdk  # type: ignore
        from sentry_sdk.integrations.fastapi import FastApiIntegration  # type: ignore
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration  # type: ignore
    except ImportError:
        logger.info("sentry-sdk not installed; skipping observability")
        return

    sentry_sdk.init(
        dsn=Config.SENTRY_DSN,
        environment=Config.ENVIRONMENT,
        release=Config.APP_VERSION,
        traces_sample_rate=0.1,
        profiles_sample_rate=0.1,
        integrations=[FastApiIntegration(), SqlalchemyIntegration()],
    )
    _initialized = True
    logger.info("✅ Sentry initialized (env=%s)", Config.ENVIRONMENT)
