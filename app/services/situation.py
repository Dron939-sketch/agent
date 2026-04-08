"""Ситуационная осведомлённость: контекстные слои реального времени.

Sprint 10: Фреди понимает текущий момент — время суток, день недели,
погоду, приближающиеся события, и адаптирует тон и содержание ответов.

Интегрируется в ContextAggregator как дополнительный блок system prompt.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import aiohttp

from app.core.config import Config
from app.core.logging import get_logger
from app.db import GoalRepository, HabitRepository, KnowledgeRepository, session_scope

logger = get_logger(__name__)

# Русские названия дней недели и месяцев
_WEEKDAYS = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
_MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня",
           "июля", "августа", "сентября", "октября", "ноября", "декабря"]

# Периоды суток
_TIME_PERIODS = {
    range(5, 9): ("раннее утро", "Пользователь встал рано или не спал. Будь мягким."),
    range(9, 12): ("утро", "Продуктивное время. Можно быть энергичным."),
    range(12, 14): ("день, обеденное время", "Пользователь может быть занят обедом."),
    range(14, 18): ("день", "Рабочее время. Будь конкретным."),
    range(18, 22): ("вечер", "Время отдыха. Можно быть расслабленнее."),
    range(22, 24): ("поздний вечер", "Пора отдыхать. Напомни, если завтра рано вставать."),
    range(0, 5): ("ночь", "Очень поздно. Предложи поспать, если нет срочных дел."),
}


def _get_time_period(hour: int) -> tuple[str, str]:
    for hours, (name, advice) in _TIME_PERIODS.items():
        if hour in hours:
            return name, advice
    return "день", ""


async def _get_weather(city: str = "Moscow") -> str | None:
    """Получает текущую погоду через OpenWeather API."""
    key = Config.OPENWEATHER_API_KEY if hasattr(Config, "OPENWEATHER_API_KEY") else None
    if not key:
        return None
    try:
        url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={key}&units=metric&lang=ru"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=5) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                desc = data.get("weather", [{}])[0].get("description", "")
                temp = data.get("main", {}).get("temp", "?")
                return f"{desc}, {temp}°C"
    except Exception:
        return None


async def build_situation_context(user_id: str, *, tz_offset: int = 3) -> str:
    """Собирает ситуационный контекст для system prompt.

    Returns строку для вставки в промпт или "" если контекста нет.
    """
    tz = timezone(timedelta(hours=tz_offset))
    now = datetime.now(tz)
    parts: list[str] = ["СИТУАЦИОННЫЙ КОНТЕКСТ:"]

    # 1. Время и дата
    weekday = _WEEKDAYS[now.weekday()]
    month = _MONTHS[now.month - 1]
    time_period, time_advice = _get_time_period(now.hour)
    is_weekend = now.weekday() >= 5

    parts.append(
        f"- Сейчас: {weekday}, {now.day} {month}, {now.strftime('%H:%M')} ({time_period})"
    )
    if is_weekend:
        parts.append("- Выходной день — пользователь скорее всего отдыхает")
    if time_advice:
        parts.append(f"- {time_advice}")

    # 2. Погода (опционально)
    weather = await _get_weather()
    if weather:
        parts.append(f"- Погода: {weather}")

    # 3. Ближайшие дедлайны (цели)
    try:
        async with session_scope() as session:
            goals = await GoalRepository(session).list_active(user_id)
        upcoming: list[str] = []
        for g in goals:
            if g.target_date:
                days_left = (g.target_date - datetime.utcnow()).days
                if 0 <= days_left <= 7:
                    upcoming.append(f"«{g.title}» через {days_left} дн.")
        if upcoming:
            parts.append(f"- Ближайшие дедлайны: {'; '.join(upcoming)}")
    except Exception:
        pass

    # 4. Невыполненные привычки за сегодня
    try:
        async with session_scope() as session:
            habits = await HabitRepository(session).list(user_id)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).replace(tzinfo=None)
        undone = [
            h.title for h in habits
            if h.cadence == "daily" and (not h.last_check_at or h.last_check_at < today_start)
        ]
        if undone and now.hour >= 12:  # Показываем только после обеда
            parts.append(f"- Привычки не отмечены сегодня: {', '.join(undone[:3])}")
    except Exception:
        pass

    # 5. Ключевые факты из Knowledge Graph (top-3 по важности)
    try:
        async with session_scope() as session:
            repo = KnowledgeRepository(session)
            facts = await repo.get_facts(user_id, limit=3, min_confidence=0.7)
        if facts:
            key_facts = [f"{f.subject} {f.predicate} {f.object}" for f in facts[:3]]
            parts.append(f"- Ключевые факты: {'; '.join(key_facts)}")
    except Exception:
        pass

    if len(parts) <= 1:
        return ""  # Только заголовок — нечего показывать

    parts.append("Учитывай ситуацию в тоне и содержании ответа.")
    return "\n".join(parts)
