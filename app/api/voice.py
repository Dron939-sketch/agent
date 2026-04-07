"""Voice endpoints: STT (Deepgram→Yandex auto), TTS (Yandex), semantic endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.auth import AuthenticatedUser
from app.services.voice import VoiceService
from app.services.voice_pkg import SemanticEndpointDetector

from .deps import get_current_user

router = APIRouter(prefix="/api/voice", tags=["voice"])

_detector = SemanticEndpointDetector()


class STTResponse(BaseModel):
    text: str
    provider: str


class TTSRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    voice: str = "jane"


class EndpointRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    silence_ms: int = 0


class EndpointResponse(BaseModel):
    is_complete: bool
    confidence: float
    reason: str


def _service() -> VoiceService:
    return VoiceService()


@router.post("/stt", response_model=STTResponse)
async def speech_to_text(
    audio: UploadFile = File(...),
    _user: AuthenticatedUser = Depends(get_current_user),
) -> STTResponse:
    raw = await audio.read()
    text, provider = await _service().transcribe(
        raw,
        content_type=audio.content_type or "audio/webm",
        language="ru",
    )
    if not text:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "no STT provider configured (set DEEPGRAM_API_KEY or YANDEX_API_KEY)",
        )
    return STTResponse(text=text, provider=provider)


@router.post("/tts")
async def text_to_speech(
    body: TTSRequest,
    _user: AuthenticatedUser = Depends(get_current_user),
) -> Response:
    audio = await _service().synthesize(body.text, voice=body.voice)
    if not audio:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "TTS unavailable (set YANDEX_API_KEY)",
        )
    return Response(content=audio, media_type="audio/ogg")


@router.post("/endpoint-check", response_model=EndpointResponse)
async def endpoint_check(
    body: EndpointRequest,
    _user: AuthenticatedUser = Depends(get_current_user),
) -> EndpointResponse:
    """Подсказка фронту: закончил ли пользователь мысль (без LLM)."""
    result = _detector.detect(body.text, silence_ms=body.silence_ms)
    return EndpointResponse(
        is_complete=result.is_complete,
        confidence=result.confidence,
        reason=result.reason,
    )
