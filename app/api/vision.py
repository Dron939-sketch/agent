"""Vision endpoint: распознавание изображений через Claude/OpenAI vision.

Принимает multipart upload + опциональный текстовый вопрос.
Использует первого доступного провайдера: Anthropic → OpenAI.
Если ни один не настроен — отдаёт 503.
"""

from __future__ import annotations

import base64

import aiohttp
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel

from app.auth import AuthenticatedUser
from app.core.config import Config
from app.core.logging import get_logger

from .deps import get_current_user

logger = get_logger(__name__)

router = APIRouter(prefix="/api/vision", tags=["vision"])


class VisionResponse(BaseModel):
    text: str
    provider: str


def _detect_media_type(filename: str | None, declared: str | None) -> str:
    if declared and declared.startswith("image/"):
        return declared
    name = (filename or "").lower()
    if name.endswith(".png"):
        return "image/png"
    if name.endswith(".jpg") or name.endswith(".jpeg"):
        return "image/jpeg"
    if name.endswith(".webp"):
        return "image/webp"
    if name.endswith(".gif"):
        return "image/gif"
    return "image/png"


async def _ask_anthropic(b64: str, media_type: str, question: str) -> str:
    headers = {
        "x-api-key": Config.ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    payload = {
        "model": "claude-sonnet-4-6",
        "max_tokens": 800,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": b64,
                        },
                    },
                    {"type": "text", "text": question or "Опиши изображение по-русски."},
                ],
            }
        ],
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers,
            json=payload,
            timeout=60,
        ) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise HTTPException(resp.status, f"anthropic: {body[:300]}")
            data = await resp.json()
    parts = [b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"]
    return "".join(parts)


async def _ask_openai(b64: str, media_type: str, question: str) -> str:
    headers = {
        "Authorization": f"Bearer {Config.OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "gpt-4o-mini",
        "max_tokens": 800,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": question or "Опиши изображение по-русски."},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{media_type};base64,{b64}"},
                    },
                ],
            }
        ],
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=60,
        ) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise HTTPException(resp.status, f"openai: {body[:300]}")
            data = await resp.json()
    return data["choices"][0]["message"]["content"]


@router.post("/analyze", response_model=VisionResponse)
async def analyze(
    image: UploadFile = File(...),
    question: str = Form(default=""),
    _user: AuthenticatedUser = Depends(get_current_user),
) -> VisionResponse:
    raw = await image.read()
    if not raw:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "empty image")
    b64 = base64.b64encode(raw).decode("ascii")
    media_type = _detect_media_type(image.filename, image.content_type)

    if Config.ANTHROPIC_API_KEY:
        try:
            text = await _ask_anthropic(b64, media_type, question)
            return VisionResponse(text=text, provider="anthropic")
        except HTTPException:
            raise
        except Exception as exc:
            logger.warning("anthropic vision failed: %s", exc)

    if Config.OPENAI_API_KEY:
        try:
            text = await _ask_openai(b64, media_type, question)
            return VisionResponse(text=text, provider="openai")
        except HTTPException:
            raise
        except Exception as exc:
            logger.warning("openai vision failed: %s", exc)

    raise HTTPException(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "no vision provider configured (set ANTHROPIC_API_KEY or OPENAI_API_KEY)",
    )
