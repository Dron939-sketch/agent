"""FastAPI factory: собирает приложение из роутеров `app.api.*`."""

from __future__ import annotations

import os
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
from . import coach as coach_router
from . import dashboard as dashboard_router
from . import feedback as feedback_router
from . import push as push_router
from . import reminders as reminders_router
from . import system as system_router
from . import triggers as triggers_router
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

    # Sprint 8: Register reminder handler with scheduler
    from app.services.scheduler import TaskScheduler
    from app.services.tasks import get_reminder_manager

    scheduler = TaskScheduler()
    manager = get_reminder_manager()
    scheduler.register("reminder", manager.handle_reminder)
    await scheduler.start()

    # Sprint 6: Start proactive trigger engine
    from app.services.triggers import get_trigger_engine
    from app.services.triggers.builtin import register_builtin_triggers
    from app.services.triggers.monitors import register_monitor_triggers

    trigger_engine = get_trigger_engine()
    register_builtin_triggers(trigger_engine)
    register_monitor_triggers(trigger_engine)
    await trigger_engine.start()

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
        await trigger_engine.stop()
        await scheduler.stop()
        await autonomy.stop()
        await dispose_db()
        logger.info("👋 shutdown complete")


def _resolve_cors_origins() -> list[str]:
    """Явный список фронтовых origin'ов.

    Render иногда капризничает с `allow_origin_regex` на preflight'ах
    (особенно, когда контейнер ещё прогревается). Явный список — самый
    надёжный вариант: браузер получает точное значение
    `Access-Control-Allow-Origin` и не отбрасывает ответ.
    """
    defaults = [
        "https://agent-frontend-fxtv.onrender.com",
        "https://agent-frontend.onrender.com",
        "https://agent-ynlg.onrender.com",
        "http://localhost:3000",
        "http://localhost:8000",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8000",
    ]
    extra = os.environ.get("CORS_ALLOW_ORIGINS", "").strip()
    if extra:
        defaults.extend(
            origin.strip().rstrip("/")
            for origin in extra.split(",")
            if origin.strip()
        )
    # dedupe, stable order
    seen: set[str] = set()
    unique: list[str] = []
    for origin in defaults:
        if origin not in seen:
            seen.add(origin)
            unique.append(origin)
    return unique


def create_app() -> FastAPI:
    app = FastAPI(
        title=Config.APP_NAME,
        version=Config.APP_VERSION,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_resolve_cors_origins(),
        allow_origin_regex=r"https?://(.*\.onrender\.com|localhost(:\d+)?|127\.0\.0\.1(:\d+)?)",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],
        max_age=600,
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
    app.include_router(dashboard_router.router)
    app.include_router(coach_router.router)
    app.include_router(reminders_router.router)
    app.include_router(triggers_router.router)

    return app


app = create_app()

__all__ = ["app", "create_app"]
