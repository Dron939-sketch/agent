"""Voice endpoints: STT, TTS (sync + stream), full-loop, semantic endpoint, voice catalog."""

from __future__ import annotations

import re
from collections.abc import AsyncIterator

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthenticatedUser
from app.core.logging import get_logger
from app.db import ConversationRepository, EmotionRepository
from app.services.context import ContextAggregator
from app.services.emotion import EmotionService
from app.services.intents import detect_intent
from app.services.knowledge import freddy_persona
from app.services.llm import ChatMessage, default_router
from app.services.memory import MemoryRecord, default_memory
from app.services.voice import VoiceService
from app.services.voice_pkg import SemanticEndpointDetector

from .deps import get_current_user, get_session

logger = get_logger(__name__)

router = APIRouter(prefix="/api/voice", tags=["voice"])

_detector = SemanticEndpointDetector()

DEFAULT_VOICE = "madirus"  # Сербский баритон, ~ Милош Бикович

# Wake word варианты для очистки транскрипта перед отправкой в LLM
_WAKE_WORD_RE = re.compile(
    r"^[\s,]*(?:фреди|фредди|фрэди|фрэдди|freddy|fredi)[\s,!.?]*",
    re.IGNORECASE,
)


def strip_wake_word(text: str) -> str:
    """Удаляет wake word 'Фреди' из начала транскрипта."""
    cleaned = _WAKE_WORD_RE.sub("", text).strip()
    return cleaned if cleaned else text


class STTResponse(BaseModel):
    text: str
    provider: str


class TTSRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    voice: str = DEFAULT_VOICE
    tone: str = "warm"
    prefer: str = Field(default="auto", pattern="^(auto|elevenlabs|yandex)$")


class EndpointRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    silence_ms: int = 0


class EndpointResponse(BaseModel):
    is_complete: bool
    confidence: float
    reason: str


class FullLoopResponse(BaseModel):
    transcript: str
    transcript_provider: str
    voice_emotion: dict | None = None
    text_emotion: dict | None = None
    fused_emotion: str | None = None
    fused_tone: str | None = None
    reply: str
    reply_model: str
    intent: str | None = None
    audio_url: str | None = None


class VoiceInfo(BaseModel):
    id: str
    label: str
    gender: str | None = None
    accent: str | None = None
    default: bool = False


def _service() -> VoiceService:
    return VoiceService()


def _base_system() -> str:
    persona = freddy_persona()
    if persona:
        return persona
    return "Ты Фреди, дружелюбный и всемогущий AI-помощник."


@router.get("/voices", response_model=list[VoiceInfo])
async def list_voices() -> list[VoiceInfo]:
    """Каталог доступных голосов TTS."""
    voices = _service().list_voices()
    return [
        VoiceInfo(
            id=vid,
            label=v.get("label", vid),
            gender=v.get("gender"),
            accent=v.get("accent"),
            default=v.get("default", False),
        )
        for vid, v in voices.items()
    ]


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
    audio, provider = await _service().synthesize(
        body.text, voice=body.voice, tone=body.tone, prefer=body.prefer
    )
    if not audio:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "TTS unavailable (set ELEVENLABS_API_KEY or YANDEX_API_KEY)",
        )
    media = "audio/mpeg" if provider == "elevenlabs" else "audio/ogg"
    return Response(
        content=audio,
        media_type=media,
        headers={
            "X-TTS-Provider": provider,
            "X-TTS-Voice": body.voice,
        },
    )


@router.post("/tts/stream")
async def text_to_speech_stream(
    body: TTSRequest,
    _user: AuthenticatedUser = Depends(get_current_user),
) -> StreamingResponse:
    """Streaming TTS — отдаёт chunks по мере генерации."""
    voice_service = _service()

    async def stream_audio() -> AsyncIterator[bytes]:
        async for chunk in voice_service.synthesize_stream(
            body.text, voice=body.voice, tone=body.tone
        ):
            yield chunk

    return StreamingResponse(
        stream_audio(),
        media_type="audio/mpeg",
        headers={"X-TTS-Voice": body.voice},
    )


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


@router.post("/full-loop", response_model=FullLoopResponse)
async def full_loop(
    background: BackgroundTasks,
    audio: UploadFile = File(...),
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> FullLoopResponse:
    """Единый endpoint: audio → STT + voice emotion → fusion → LLM → ответ."""
    raw = await audio.read()
    if not raw:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "empty audio")

    voice_service = _service()

    transcript, stt_provider = await voice_service.transcribe(
        raw, content_type=audio.content_type or "audio/webm"
    )
    if not transcript:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "STT failed — no provider or empty result",
        )

    voice_emo: dict | None = None
    try:
        voice_emo = await voice_service.voice_emotion(
            raw, content_type=audio.content_type or "audio/webm"
        )
    except Exception as exc:
        logger.warning("voice emotion failed: %s", exc)

    # Удаляем wake word из начала транскрипта для обработки
    clean_transcript = strip_wake_word(transcript)

    intent = detect_intent(clean_transcript)
    intent_reply: str | None = None
    if intent.type == "remember" and intent.payload:
        await default_memory().add(
            [
                MemoryRecord(
                    id="",
                    text=intent.payload,
                    user_id=user.user_id,
                    metadata={"kind": "fact", "source": "voice"},
                )
            ]
        )
        intent_reply = f"Запомнил: «{intent.payload}»."
    elif intent.type == "forget" and intent.payload:
        removed = await default_memory().forget(user.user_id, intent.payload)
        intent_reply = (
            f"Удалил {removed} запис(и) про «{intent.payload}»."
            if removed
            else f"Ничего такого в памяти не нашёл — {intent.payload}."
        )

    convos = ConversationRepository(session)
    await convos.add(user.user_id, "user", transcript)

    emotion_service = EmotionService(default_router())
    text_emo = emotion_service.detect_from_text(clean_transcript)
    aggregator = ContextAggregator(session, emotion_service=emotion_service)
    full_ctx = await aggregator.get_full_context(user.user_id, clean_transcript)

    fused_primary = text_emo.primary
    fused_tone = text_emo.tone
    if voice_emo and voice_emo.get("confidence", 0) > 0.6:
        fused_primary = voice_emo["primary"]

    try:
        await EmotionRepository(session).add(
            user_id=user.user_id,
            primary=fused_primary,
            intensity=voice_emo["intensity"] if voice_emo else text_emo.intensity,
            confidence=voice_emo["confidence"] if voice_emo else text_emo.confidence,
            tone=fused_tone,
            needs_support=text_emo.needs_support,
            source="both" if voice_emo else "text",
        )
    except Exception as exc:
        logger.warning("emotion log failed: %s", exc)

    if intent_reply is not None:
        reply_text = intent_reply
        reply_model = "intent-handler"
    else:
        history_rows = full_ctx.history[:-1] if full_ctx.history else []
        system_text = ContextAggregator.format_for_prompt(full_ctx, _base_system())
        msgs: list[ChatMessage] = [ChatMessage(role="system", content=system_text)]
        for m in history_rows:
            msgs.append(ChatMessage(role=m["role"], content=m["content"]))  # type: ignore[arg-type]
        msgs.append(ChatMessage(role="user", content=clean_transcript))

        response = await default_router().chat(msgs, profile="smart")  # type: ignore[arg-type]
        reply_text = response.text
        reply_model = response.model

    await convos.add(user.user_id, "assistant", reply_text)

    async def _store_memory():
        try:
            await default_memory().add(
                [
                    MemoryRecord(id="", text=transcript, user_id=user.user_id, metadata={"role": "user", "voice": True}),
                    MemoryRecord(id="", text=reply_text, user_id=user.user_id, metadata={"role": "assistant"}),
                ]
            )
        except Exception:
            pass

    background.add_task(_store_memory)

    return FullLoopResponse(
        transcript=transcript,
        transcript_provider=stt_provider,
        voice_emotion=voice_emo,
        text_emotion=text_emo.to_dict(),
        fused_emotion=fused_primary,
        fused_tone=fused_tone,
        reply=reply_text,
        reply_model=reply_model,
        intent=intent.type if intent.type != "none" else None,
        audio_url="/api/voice/tts/stream",
    )
