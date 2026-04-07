"""Системные роуты: health, version."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.config import Config

router = APIRouter(tags=["system"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/version")
async def version() -> dict[str, str]:
    return {"name": Config.APP_NAME, "version": Config.APP_VERSION}
