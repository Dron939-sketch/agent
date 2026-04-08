"""Sprint 8 tests: Russian date parser, intents (remind/task), ReminderManager."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret")

from app.services.tasks.date_parser import ParsedDateTime, parse_russian_datetime  # noqa: E402
from app.services.intents import detect_intent  # noqa: E402


# ======== Date Parser: relative times ========


def test_parse_cherez_2_chasa() -> None:
    result = parse_russian_datetime("через 2 часа позвонить маме", tz_offset=3)
    assert result.dt is not None
    assert result.confidence >= 0.8
    delta = result.dt - datetime.utcnow()
    assert 1.5 * 3600 < delta.total_seconds() < 2.5 * 3600
    assert "позвонить маме" in result.remaining_text


def test_parse_cherez_30_minut() -> None:
    result = parse_russian_datetime("через 30 минут проверить почту", tz_offset=3)
    assert result.dt is not None
    delta = result.dt - datetime.utcnow()
    assert 25 * 60 < delta.total_seconds() < 35 * 60


def test_parse_cherez_polchasa() -> None:
    result = parse_russian_datetime("через полчаса", tz_offset=3)
    assert result.dt is not None
    delta = result.dt - datetime.utcnow()
    assert 25 * 60 < delta.total_seconds() < 35 * 60


def test_parse_cherez_3_dnya() -> None:
    result = parse_russian_datetime("через 3 дня сдать отчёт", tz_offset=3)
    assert result.dt is not None
    delta = result.dt - datetime.utcnow()
    assert 2.5 * 86400 < delta.total_seconds() < 3.5 * 86400


# ======== Date Parser: absolute dates ========


def test_parse_zavtra_v_9() -> None:
    result = parse_russian_datetime("завтра в 9 утра встреча", tz_offset=3)
    assert result.dt is not None
    assert result.confidence >= 0.7
    # Should be tomorrow 9:00 Moscow → 6:00 UTC
    expected_hour_utc = 9 - 3  # 6:00 UTC
    assert result.dt.hour == expected_hour_utc
    assert "встреча" in result.remaining_text


def test_parse_poslezavtra() -> None:
    result = parse_russian_datetime("послезавтра вечером", tz_offset=3)
    assert result.dt is not None
    # "вечером" = 19:00 local = 16:00 UTC
    assert result.dt.hour == 16


def test_parse_v_pyatnicu() -> None:
    result = parse_russian_datetime("в пятницу в 15:00 дедлайн", tz_offset=3)
    assert result.dt is not None
    # Should be next Friday
    assert result.dt.weekday() == 4  # Friday = 4 (but stored as UTC, day might shift)
    assert result.confidence >= 0.7


# ======== Date Parser: recurrence ========


def test_parse_kazhdyj_den() -> None:
    result = parse_russian_datetime("каждый день пить воду", tz_offset=3)
    assert result.recurrence == "daily"
    assert "пить воду" in result.remaining_text


def test_parse_ezhenedelno() -> None:
    result = parse_russian_datetime("еженедельно отчёт", tz_offset=3)
    assert result.recurrence == "weekly"


def test_parse_no_time() -> None:
    result = parse_russian_datetime("купить молоко", tz_offset=3)
    assert result.dt is None
    assert result.recurrence is None
    assert result.confidence == 0.0


# ======== Intent Detection: new types ========


def test_intent_remind_basic() -> None:
    intent = detect_intent("напомни через 2 часа позвонить маме")
    assert intent.type == "remind"
    assert "через 2 часа позвонить маме" in intent.payload


def test_intent_remind_ne_day_zabyt() -> None:
    intent = detect_intent("не дай мне забыть, купить хлеб завтра")
    assert intent.type == "remind"
    assert "купить хлеб завтра" in intent.payload


def test_intent_remind_postavj() -> None:
    intent = detect_intent("поставь мне напоминание завтра в 9 позвонить")
    assert intent.type == "remind"


def test_intent_task_create() -> None:
    intent = detect_intent("добавь задачу — купить продукты")
    assert intent.type == "task_create"
    assert "купить продукты" in intent.payload


def test_intent_task_list() -> None:
    intent = detect_intent("какие у меня задачи")
    assert intent.type == "task_list"


def test_intent_task_list_napominaniya() -> None:
    intent = detect_intent("покажи мои напоминания")
    assert intent.type == "task_list"


def test_intent_task_cancel() -> None:
    intent = detect_intent("удали задачу про отчёт")
    assert intent.type == "task_cancel"
    assert "отчёт" in intent.payload


def test_intent_chto_nado_sdelat() -> None:
    intent = detect_intent("что мне нужно сделать")
    assert intent.type == "task_list"


# ======== Existing intents still work ========


def test_intent_remember_still_works() -> None:
    intent = detect_intent("запомни, что я работаю на Python")
    assert intent.type == "remember"
    assert "Python" in intent.payload


def test_intent_goal_still_works() -> None:
    intent = detect_intent("моя цель — выучить Go")
    assert intent.type == "goal_set"
    assert "Go" in intent.payload


def test_intent_none() -> None:
    intent = detect_intent("привет, как дела?")
    assert intent.type == "none"
