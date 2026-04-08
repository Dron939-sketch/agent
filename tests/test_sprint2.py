"""Тесты Sprint 2: ElevenLabs/Hume/Replicate без сетевых вызовов."""

from __future__ import annotations

import pytest

from app.services.image import ReplicateImageGen
from app.services.voice_pkg.elevenlabs import ElevenLabsTTS
from app.services.voice_pkg.hume import HUME_TO_PLUTCHIK, HumeVoiceEmotion


# ======== ElevenLabs ========


def test_elevenlabs_not_configured_without_key() -> None:
    client = ElevenLabsTTS(api_key="")
    assert client.is_configured() is False


def test_elevenlabs_voice_settings_warm() -> None:
    client = ElevenLabsTTS(api_key="dummy")
    s = client._voice_settings("warm")
    assert 0 <= s["stability"] <= 1
    assert 0 <= s["similarity_boost"] <= 1
    assert 0 <= s["style"] <= 1
    assert s["use_speaker_boost"] is True


def test_elevenlabs_voice_settings_energetic_more_style() -> None:
    client = ElevenLabsTTS(api_key="dummy")
    warm = client._voice_settings("warm")
    energetic = client._voice_settings("energetic")
    # Энергичный голос — выше style, ниже stability
    assert energetic["style"] > warm["style"]
    assert energetic["stability"] < warm["stability"]


@pytest.mark.asyncio
async def test_elevenlabs_synthesize_returns_none_without_key() -> None:
    client = ElevenLabsTTS(api_key="")
    out = await client.synthesize("test", tone="warm")
    assert out is None


# ======== Hume ========


def test_hume_not_configured_without_key() -> None:
    h = HumeVoiceEmotion(api_key="")
    assert h.is_configured() is False


@pytest.mark.asyncio
async def test_hume_returns_none_without_key() -> None:
    h = HumeVoiceEmotion(api_key="")
    out = await h.analyze(b"fake audio bytes")
    assert out is None


def test_hume_to_plutchik_mapping_complete() -> None:
    """Проверяем, что все mapping-эмоции — валидные Plutchik."""
    from app.services.emotion import VALID_EMOTIONS

    for hume_name, plutchik in HUME_TO_PLUTCHIK.items():
        assert plutchik in VALID_EMOTIONS, f"{hume_name} → {plutchik} not in VALID_EMOTIONS"


def test_hume_aggregate_handles_empty_predictions() -> None:
    h = HumeVoiceEmotion(api_key="dummy")
    assert h._aggregate([]) is None
    assert h._aggregate([{}]) is None


def test_hume_aggregate_returns_top_emotion() -> None:
    h = HumeVoiceEmotion(api_key="dummy")
    fake_predictions = [
        {
            "results": {
                "predictions": [
                    {
                        "models": {
                            "prosody": {
                                "grouped_predictions": [
                                    {
                                        "predictions": [
                                            {
                                                "emotions": [
                                                    {"name": "Joy", "score": 0.8},
                                                    {"name": "Calmness", "score": 0.5},
                                                    {"name": "Sadness", "score": 0.1},
                                                ]
                                            }
                                        ]
                                    }
                                ]
                            }
                        }
                    }
                ]
            }
        }
    ]
    result = h._aggregate(fake_predictions)
    assert result is not None
    assert result["primary"] == "joy"
    assert result["primary_raw"] == "Joy"
    assert result["intensity"] >= 5
    assert len(result["top_5"]) == 3


# ======== Replicate ========


def test_replicate_not_configured_without_token() -> None:
    gen = ReplicateImageGen(api_token="")
    assert gen.is_configured() is False


@pytest.mark.asyncio
async def test_replicate_returns_none_without_token() -> None:
    gen = ReplicateImageGen(api_token="")
    urls = await gen.generate("a cat in space")
    assert urls is None


def test_replicate_extract_urls() -> None:
    gen = ReplicateImageGen(api_token="dummy")
    assert gen._extract_urls(["http://a.png", "http://b.png"]) == [
        "http://a.png",
        "http://b.png",
    ]
    assert gen._extract_urls("http://single.png") == ["http://single.png"]
    assert gen._extract_urls(None) == []
    assert gen._extract_urls({}) == []


# ======== VoiceService integration ========


@pytest.mark.asyncio
async def test_voice_service_synthesize_falls_back_when_no_keys() -> None:
    from app.services.voice import VoiceService

    vs = VoiceService()
    audio, provider = await vs.synthesize("test", tone="warm", prefer="auto")
    # без ключей оба провайдера вернут None
    assert audio is None
    assert provider == "none"
