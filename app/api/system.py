"""Системные роуты: root landing, health, version, keepalive."""

from __future__ import annotations

import time

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import text

from app.core.config import Config
from app.db import session_scope

router = APIRouter(tags=["system"])

_STARTED_AT = time.time()


_LANDING_HTML = """<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Фреди AI · API</title>
<style>
:root {{ color-scheme: dark; }}
* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  min-height: 100vh;
  font-family: -apple-system, "Segoe UI", Inter, sans-serif;
  color: #e2e8f0;
  background:
    radial-gradient(ellipse at 20% 10%, rgba(34,211,238,.18), transparent 55%),
    radial-gradient(ellipse at 80% 20%, rgba(168,85,247,.22), transparent 55%),
    radial-gradient(ellipse at 60% 85%, rgba(244,114,182,.15), transparent 55%),
    linear-gradient(180deg,#05060f,#070919);
  display: grid;
  place-items: center;
  padding: 24px;
}}
.card {{
  width: min(640px, 100%);
  border: 1px solid rgba(255,255,255,.12);
  background: rgba(18,21,45,.55);
  backdrop-filter: blur(20px);
  border-radius: 20px;
  padding: 32px;
  box-shadow: 0 0 60px rgba(168,85,247,.25), inset 0 1px 0 rgba(255,255,255,.08);
}}
.logo {{
  width: 44px; height: 44px; border-radius: 12px; margin-bottom: 16px;
  background: linear-gradient(135deg,#22d3ee,#a855f7,#f472b6);
  box-shadow: 0 0 40px rgba(168,85,247,.4);
}}
h1 {{
  margin: 0 0 4px;
  font-size: 28px;
  background: linear-gradient(135deg,#22d3ee,#a855f7,#f472b6);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}}
.sub {{ color:#94a3b8; font-size:13px; margin-bottom:20px; }}
.badge {{
  display:inline-flex; gap:6px; align-items:center;
  padding:4px 10px; border-radius:999px;
  background: rgba(34,197,94,.15); color:#86efac;
  border:1px solid rgba(34,197,94,.35);
  font-size:12px;
}}
ul {{ list-style:none; padding:0; margin:20px 0 0; display:grid; gap:8px; }}
li a {{
  display:flex; justify-content:space-between; align-items:center;
  padding:10px 14px; border-radius:12px;
  background: rgba(255,255,255,.04);
  border:1px solid rgba(255,255,255,.08);
  color:#e2e8f0; text-decoration:none;
  font-family: ui-monospace, "JetBrains Mono", monospace; font-size:13px;
  transition: all .15s;
}}
li a:hover {{ background: rgba(168,85,247,.18); border-color: rgba(168,85,247,.4); }}
.pill {{ font-size:11px; color:#94a3b8; }}
.foot {{ margin-top:20px; font-size:11px; color:#64748b; text-align:center; }}
</style>
</head>
<body>
<div class="card">
  <div class="logo"></div>
  <h1>Фреди AI</h1>
  <div class="sub">{name} · v{version} · env: {env}</div>
  <span class="badge">● online</span>
  <ul>
    <li><a href="/docs">/docs <span class="pill">Swagger UI</span></a></li>
    <li><a href="/redoc">/redoc <span class="pill">ReDoc</span></a></li>
    <li><a href="/health">/health <span class="pill">healthcheck</span></a></li>
    <li><a href="/version">/version <span class="pill">build info</span></a></li>
    <li><a href="/keepalive">/keepalive <span class="pill">no-sleep ping</span></a></li>
    <li><a href="/api/auth/me">/api/auth/me <span class="pill">требует токен</span></a></li>
  </ul>
  <div class="foot">всемогущий мульти-агентный AI-помощник</div>
</div>
</body>
</html>
"""


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def root() -> HTMLResponse:
    html = _LANDING_HTML.format(
        name=Config.APP_NAME,
        version=Config.APP_VERSION,
        env=Config.ENVIRONMENT,
    )
    return HTMLResponse(content=html)


@router.get("/favicon.ico", include_in_schema=False)
async def favicon() -> Response:
    """Прозрачный 1×1 PNG."""
    transparent_png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8"
        b"\x0f\x00\x00\x01\x01\x00\x01\x00\x18\xdd\x8d\xb4\x00\x00\x00\x00"
        b"IEND\xaeB`\x82"
    )
    return Response(content=transparent_png, media_type="image/png")


@router.get("/health")
async def health() -> dict[str, object]:
    """Liveness — отдаёт 200 если процесс жив."""
    return {
        "status": "ok",
        "uptime_seconds": int(time.time() - _STARTED_AT),
    }


@router.get("/ready")
async def ready() -> dict[str, object]:
    """Readiness — проверяет БД-коннект. 200 если БД отвечает, 503 если нет."""
    try:
        async with session_scope() as session:
            await session.execute(text("SELECT 1"))
        return {"status": "ready", "database": "ok"}
    except Exception as exc:
        return {"status": "degraded", "database": "fail", "error": str(exc)[:200]}


@router.get("/keepalive", include_in_schema=False)
async def keepalive() -> dict[str, str]:
    """Лёгкий ping для удержания сервиса от засыпания на free-tier хостингах."""
    return {"status": "alive"}


@router.get("/version")
async def version() -> dict[str, str]:
    return {
        "name": Config.APP_NAME,
        "version": Config.APP_VERSION,
        "environment": Config.ENVIRONMENT,
    }
