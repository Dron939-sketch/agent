"""FastAPI factory: собирает приложение из роутеров `app.api.*`."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.autonomy import get_autonomy_loop
from app.core.config import Config
from app.core.logging import get_logger, setup_logging
from app.core.observability import init_sentry
from app.db import dispose_db, init_db
from app.plugins import load_plugins

from . import agents as agents_router
from . import auth as auth_router
from . import brief as brief_router
from . import chat as chat_router
from . import feedback as feedback_router
from . import push as push_router
from . import system as system_router
from . import vision as vision_router
from . import voice as voice_router

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):  # noqa: ANN201
    setup_logging()
    init_sentry()
    Config.ensure_dirs()
    await init_db()
    plugins = load_plugins()

    autonomy = get_autonomy_loop()
    await autonomy.start()

    logger.info(
        "🚀 %s %s started (env=%s, plugins=%d, self_url=%s)",
        Config.APP_NAME,
        Config.APP_VERSION,
        Config.ENVIRONMENT,
        len(plugins),
        autonomy.self_url or "—",
    )
    try:
        yield
    finally:
        await autonomy.stop()
        await dispose_db()
        logger.info("👋 shutdown complete")


def create_app() -> FastAPI:
    app = FastAPI(
        title=Config.APP_NAME,
        version=Config.APP_VERSION,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"https?://(.*\.onrender\.com|localhost(:\d+)?|127\.0\.0\.1(:\d+)?)",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(system_router.router)
    app.include_router(auth_router.router)
    app.include_router(chat_router.router)
    app.include_router(agents_router.router)
    app.include_router(voice_router.router)
    app.include_router(push_router.router)
    app.include_router(vision_router.router)
    app.include_router(feedback_router.router)
    app.include_router(brief_router.router)

    return app


app = create_app()

__all__ = ["app", "create_app"]
