"""Google Calendar интеграция.

Подключение: GOOGLE_CALENDAR_CREDENTIALS_JSON в .env
(путь к service account credentials или OAuth client JSON).

Функции:
- calendar_today: события на сегодня
- calendar_upcoming: ближайшие N событий
- calendar_create: создать событие
- calendar_free_slots: свободные слоты

Если credentials не настроены — плагин загружается, но tools возвращают ошибку.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.logging import get_logger
from app.services.tools import tool

logger = get_logger(__name__)

_CREDS_PATH = os.environ.get("GOOGLE_CALENDAR_CREDENTIALS_JSON", "")
_CALENDAR_ID = os.environ.get("GOOGLE_CALENDAR_ID", "primary")


def _get_service():
    """Lazy-loads Google Calendar API service."""
    if not _CREDS_PATH or not os.path.exists(_CREDS_PATH):
        return None
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        creds = service_account.Credentials.from_service_account_file(
            _CREDS_PATH, scopes=["https://www.googleapis.com/auth/calendar"]
        )
        return build("calendar", "v3", credentials=creds)
    except ImportError:
        logger.warning("google-api-python-client not installed. pip install google-api-python-client google-auth")
        return None
    except Exception as exc:
        logger.warning("Google Calendar init failed: %s", exc)
        return None


def _format_event(event: dict) -> str:
    """Форматирует событие в читаемую строку."""
    start = event.get("start", {}).get("dateTime") or event.get("start", {}).get("date", "")
    end = event.get("end", {}).get("dateTime") or event.get("end", {}).get("date", "")
    summary = event.get("summary", "(без названия)")
    location = event.get("location", "")

    try:
        start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
        time_str = f"{start_dt.strftime('%H:%M')}–{end_dt.strftime('%H:%M')}"
    except Exception:
        time_str = start

    loc_str = f" ({location})" if location else ""
    return f"{time_str} {summary}{loc_str}"


@tool(name="calendar_today", description="Показать события из Google Calendar на сегодня.")
async def calendar_today() -> str:
    """Возвращает список событий на сегодня."""
    service = _get_service()
    if not service:
        return "Google Calendar не настроен. Добавь GOOGLE_CALENDAR_CREDENTIALS_JSON в .env."

    now = datetime.now(timezone.utc)
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = start_of_day + timedelta(days=1)

    try:
        result = service.events().list(
            calendarId=_CALENDAR_ID,
            timeMin=start_of_day.isoformat(),
            timeMax=end_of_day.isoformat(),
            singleEvents=True,
            orderBy="startTime",
            maxResults=20,
        ).execute()

        events = result.get("items", [])
        if not events:
            return "Сегодня нет событий в календаре."
        return "События на сегодня:\n" + "\n".join(f"• {_format_event(e)}" for e in events)
    except Exception as exc:
        return f"Ошибка доступа к календарю: {exc}"


@tool(name="calendar_upcoming", description="Показать ближайшие N событий из Google Calendar.")
async def calendar_upcoming(count: int = 5) -> str:
    """Возвращает ближайшие count событий."""
    service = _get_service()
    if not service:
        return "Google Calendar не настроен."

    now = datetime.now(timezone.utc).isoformat()
    try:
        result = service.events().list(
            calendarId=_CALENDAR_ID,
            timeMin=now,
            singleEvents=True,
            orderBy="startTime",
            maxResults=min(count, 20),
        ).execute()

        events = result.get("items", [])
        if not events:
            return "Нет предстоящих событий."
        return "Ближайшие события:\n" + "\n".join(f"• {_format_event(e)}" for e in events)
    except Exception as exc:
        return f"Ошибка: {exc}"


@tool(name="calendar_create", description="Создать событие в Google Calendar.")
async def calendar_create(
    title: str,
    start_time: str,
    end_time: str,
    description: str = "",
) -> str:
    """Создаёт событие. start_time/end_time в ISO-8601.

    Пример: calendar_create("Встреча", "2025-01-15T10:00:00+03:00", "2025-01-15T11:00:00+03:00")
    """
    service = _get_service()
    if not service:
        return "Google Calendar не настроен."

    event_body = {
        "summary": title,
        "start": {"dateTime": start_time},
        "end": {"dateTime": end_time},
    }
    if description:
        event_body["description"] = description

    try:
        event = service.events().insert(calendarId=_CALENDAR_ID, body=event_body).execute()
        link = event.get("htmlLink", "")
        return f"Событие «{title}» создано. {link}"
    except Exception as exc:
        return f"Ошибка создания события: {exc}"


@tool(name="calendar_free_slots", description="Найти свободные слоты в календаре на день.")
async def calendar_free_slots(date: str = "today") -> str:
    """Возвращает свободные слоты. date: 'today', 'tomorrow', или 'YYYY-MM-DD'."""
    service = _get_service()
    if not service:
        return "Google Calendar не настроен."

    now = datetime.now(timezone.utc)
    if date == "today":
        target = now
    elif date == "tomorrow":
        target = now + timedelta(days=1)
    else:
        try:
            target = datetime.fromisoformat(date).replace(tzinfo=timezone.utc)
        except ValueError:
            return f"Неверный формат даты: {date}"

    start_of_day = target.replace(hour=6, minute=0, second=0, microsecond=0)  # рабочий день с 6 UTC
    end_of_day = target.replace(hour=20, minute=0, second=0, microsecond=0)   # до 20 UTC

    try:
        result = service.events().list(
            calendarId=_CALENDAR_ID,
            timeMin=start_of_day.isoformat(),
            timeMax=end_of_day.isoformat(),
            singleEvents=True,
            orderBy="startTime",
        ).execute()

        events = result.get("items", [])
        busy_slots: list[tuple[datetime, datetime]] = []
        for e in events:
            s = e.get("start", {}).get("dateTime")
            en = e.get("end", {}).get("dateTime")
            if s and en:
                busy_slots.append((
                    datetime.fromisoformat(s.replace("Z", "+00:00")),
                    datetime.fromisoformat(en.replace("Z", "+00:00")),
                ))

        if not busy_slots:
            return f"Весь день свободен ({start_of_day.strftime('%H:%M')}–{end_of_day.strftime('%H:%M')} UTC)."

        free: list[str] = []
        cursor = start_of_day
        for s, e in sorted(busy_slots):
            if cursor < s:
                free.append(f"{cursor.strftime('%H:%M')}–{s.strftime('%H:%M')}")
            cursor = max(cursor, e)
        if cursor < end_of_day:
            free.append(f"{cursor.strftime('%H:%M')}–{end_of_day.strftime('%H:%M')}")

        if not free:
            return "Весь рабочий день занят."
        return "Свободные слоты:\n" + "\n".join(f"• {slot}" for slot in free)
    except Exception as exc:
        return f"Ошибка: {exc}"
