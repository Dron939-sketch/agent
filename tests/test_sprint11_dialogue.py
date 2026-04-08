"""Sprint 11 tests: dialogue clarifier, confirmation detection."""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret")

from app.services.dialogue import (  # noqa: E402
    build_dialogue_instructions,
    detect_clarification_need,
    is_confirmation,
    needs_confirmation,
)


# ======== Clarification detection ========


def test_ambiguous_short_command() -> None:
    result = detect_clarification_need("сделай")
    assert result.needed is True
    assert result.reason == "ambiguous_command"


def test_ambiguous_pokazhi() -> None:
    result = detect_clarification_need("покажи")
    assert result.needed is True


def test_normal_message_no_clarification() -> None:
    result = detect_clarification_need("расскажи мне про погоду в Москве")
    assert result.needed is False


def test_yes_no_not_ambiguous() -> None:
    # "да" / "нет" are valid answers, not ambiguous
    assert detect_clarification_need("да").needed is False
    assert detect_clarification_need("нет").needed is False


# ======== Confirmation detection ========


def test_needs_confirmation_delete_all() -> None:
    result = needs_confirmation("удали все задачи")
    assert result.needed is True
    assert result.reason == "dangerous_action"


def test_needs_confirmation_forget_all() -> None:
    result = needs_confirmation("забудь всё обо мне")
    assert result.needed is True


def test_needs_confirmation_send_email() -> None:
    result = needs_confirmation("отправь письмо Ане")
    assert result.needed is True


def test_no_confirmation_normal() -> None:
    result = needs_confirmation("какая погода завтра")
    assert result.needed is False


# ======== Confirmation detection ========


def test_is_confirmation_yes() -> None:
    assert is_confirmation("да") is True
    assert is_confirmation("Да!") is True
    assert is_confirmation("конечно") is True
    assert is_confirmation("давай") is True
    assert is_confirmation("ок") is True
    assert is_confirmation("ага") is True


def test_is_confirmation_no() -> None:
    assert is_confirmation("нет") is False
    assert is_confirmation("отмена") is False
    assert is_confirmation("неа") is False


def test_is_confirmation_unclear() -> None:
    assert is_confirmation("может быть") is None
    assert is_confirmation("расскажи подробнее") is None


# ======== Dialogue instructions ========


def test_dialogue_instructions_basic() -> None:
    instr = build_dialogue_instructions()
    assert "ПРАВИЛА ДИАЛОГА:" in instr
    assert "уточняющий вопрос" in instr


def test_dialogue_instructions_with_pending_question() -> None:
    history = [
        {"role": "user", "content": "напомни"},
        {"role": "assistant", "content": "О чём напомнить?"},
    ]
    instr = build_dialogue_instructions(history)
    assert "Ты задал вопрос" in instr


def test_dialogue_instructions_no_pending_question() -> None:
    history = [
        {"role": "user", "content": "привет"},
        {"role": "assistant", "content": "Привет! Как дела."},
    ]
    instr = build_dialogue_instructions(history)
    assert "Ты задал вопрос" not in instr
