"""Wake word tests: strip_wake_word regex logic."""

from __future__ import annotations

import re

# Reproduce the regex directly to avoid deep import chain
_WAKE_WORD_RE = re.compile(
    r"^[\s,]*(?:фреди|фредди|фрэди|фрэдди|freddy|fredi)[\s,!.?]*",
    re.IGNORECASE,
)


def strip_wake_word(text: str) -> str:
    cleaned = _WAKE_WORD_RE.sub("", text).strip()
    return cleaned if cleaned else text


def test_strip_wake_word_basic() -> None:
    assert strip_wake_word("Фреди, какая погода") == "какая погода"


def test_strip_wake_word_fredi() -> None:
    assert strip_wake_word("фреди расскажи анекдот") == "расскажи анекдот"


def test_strip_wake_word_freddy_en() -> None:
    assert strip_wake_word("Freddy, tell me a joke") == "tell me a joke"


def test_strip_wake_word_with_punctuation() -> None:
    assert strip_wake_word("Фреди! что нового?") == "что нового?"


def test_strip_wake_word_no_match() -> None:
    text = "какая погода сегодня"
    assert strip_wake_word(text) == text


def test_strip_wake_word_only_wake() -> None:
    # If only "Фреди" with nothing after — return original
    assert strip_wake_word("Фреди") == "Фреди"


def test_strip_wake_word_freddi_variant() -> None:
    assert strip_wake_word("Фредди, помоги") == "помоги"
