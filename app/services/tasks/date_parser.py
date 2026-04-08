"""NLP-парсер русских дат и времени.

Поддерживает:
  - "через 2 часа", "через 30 минут", "через 3 дня"
  - "завтра", "послезавтра", "в понедельник", "в пятницу"
  - "завтра в 9", "в пятницу в 15:00", "послезавтра утром"
  - "в 15:00", "в 9 утра", "в 10 вечера"
  - "через неделю", "через месяц"
  - "каждый день", "каждую неделю" → recurrence

Timezone: принимает tz_offset (hours from UTC), по умолчанию +3 (Москва).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

# === Числа прописью ===
_WORD_TO_NUM: dict[str, int] = {
    "один": 1, "одну": 1, "одна": 1, "одного": 1,
    "два": 2, "две": 2, "двух": 2,
    "три": 3, "трёх": 3, "трех": 3,
    "четыре": 4, "четырёх": 4, "четырех": 4,
    "пять": 5, "шесть": 6, "семь": 7, "восемь": 8, "девять": 9,
    "десять": 10, "пятнадцать": 15, "двадцать": 20, "тридцать": 30,
    "полчаса": 30,  # special: "через полчаса" = 30 минут
}

# === Дни недели ===
_WEEKDAYS: dict[str, int] = {
    "понедельник": 0, "вторник": 1, "среду": 2, "среда": 2,
    "четверг": 3, "пятницу": 4, "пятница": 4,
    "субботу": 5, "суббота": 5, "воскресенье": 6, "воскресень": 6,
}

# === Время суток ===
_TIME_OF_DAY: dict[str, int] = {
    "утром": 9, "утра": 9, "утро": 9,
    "днём": 13, "днем": 13, "дня": 13,
    "вечером": 19, "вечера": 19,
    "ночью": 23, "ночи": 23,
}

# === Recurrence patterns ===
_RECURRENCE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?i)каждый\s+день|ежедневно"), "daily"),
    (re.compile(r"(?i)каждую?\s+неделю|еженедельно"), "weekly"),
    (re.compile(r"(?i)каждый\s+месяц|ежемесячно"), "monthly"),
    (re.compile(r"(?i)каждое\s+утро"), "daily"),
    (re.compile(r"(?i)каждый\s+вечер"), "daily"),
]


@dataclass(slots=True)
class ParsedDateTime:
    """Результат парсинга даты/времени."""
    dt: datetime | None  # UTC datetime
    recurrence: str | None  # daily/weekly/monthly/None
    confidence: float  # 0..1
    remaining_text: str  # Текст без временных маркеров


def _parse_num(s: str) -> int | None:
    """Парсит число: цифрами или прописью."""
    s = s.strip().lower()
    if s.isdigit():
        return int(s)
    return _WORD_TO_NUM.get(s)


def _now_local(tz_offset: int) -> datetime:
    """Текущее время в локальной таймзоне пользователя."""
    tz = timezone(timedelta(hours=tz_offset))
    return datetime.now(tz)


def _to_utc(local_dt: datetime) -> datetime:
    """Конвертирует aware datetime в UTC."""
    return local_dt.astimezone(timezone.utc).replace(tzinfo=None)


def parse_russian_datetime(
    text: str,
    *,
    tz_offset: int = 3,
) -> ParsedDateTime:
    """Парсит русский текст с временными указаниями.

    Returns ParsedDateTime с UTC datetime и опциональной recurrence.
    """
    original = text.strip()
    lower = original.lower()
    remaining = original

    # === Recurrence ===
    recurrence: str | None = None
    for pat, rec in _RECURRENCE_PATTERNS:
        m = pat.search(lower)
        if m:
            recurrence = rec
            remaining = remaining[:m.start()] + remaining[m.end():]
            lower = remaining.lower()
            break

    now = _now_local(tz_offset)
    tz = timezone(timedelta(hours=tz_offset))

    # === "через X минут/часов/дней" ===
    m = re.search(
        r"(?i)через\s+(полчаса|\d+|[а-яё]+)\s+"
        r"(минут[уы]?|мин|час(?:а|ов)?|дн(?:ей|я)|день|недел[юиь]|месяц(?:а|ев)?)",
        lower,
    )
    if m:
        num_str, unit = m.group(1), m.group(2).lower()
        if num_str == "полчаса":
            delta = timedelta(minutes=30)
        else:
            num = _parse_num(num_str)
            if num is None:
                num = 1
            if unit.startswith("мин"):
                delta = timedelta(minutes=num)
            elif unit.startswith("час"):
                delta = timedelta(hours=num)
            elif unit.startswith("дн") or unit == "день":
                delta = timedelta(days=num)
            elif unit.startswith("недел"):
                delta = timedelta(weeks=num)
            elif unit.startswith("месяц"):
                delta = timedelta(days=num * 30)
            else:
                delta = timedelta(hours=num)

        result_dt = now + delta
        remaining = remaining[:m.start()] + remaining[m.end():]
        return ParsedDateTime(
            dt=_to_utc(result_dt),
            recurrence=recurrence,
            confidence=0.9,
            remaining_text=remaining.strip(),
        )

    # === "через полчаса" standalone ===
    m = re.search(r"(?i)через\s+полчаса", lower)
    if m:
        result_dt = now + timedelta(minutes=30)
        remaining = remaining[:m.start()] + remaining[m.end():]
        return ParsedDateTime(
            dt=_to_utc(result_dt),
            recurrence=recurrence,
            confidence=0.9,
            remaining_text=remaining.strip(),
        )

    # === Extract time (e.g., "в 15:00", "в 9 утра", "в 10 вечера") ===
    target_hour: int | None = None
    target_minute: int = 0

    m_time = re.search(r"(?i)в\s+(\d{1,2}):(\d{2})", lower)
    if m_time:
        target_hour = int(m_time.group(1))
        target_minute = int(m_time.group(2))
        remaining = remaining[:m_time.start()] + remaining[m_time.end():]
        lower = remaining.lower()

    if target_hour is None:
        m_time = re.search(r"(?i)в\s+(\d{1,2})\s*(утра|дня|вечера|ночи|часов|час(?:а)?)", lower)
        if m_time:
            target_hour = int(m_time.group(1))
            period = m_time.group(2).lower()
            if period in ("вечера", "ночи") and target_hour < 12:
                target_hour += 12
            elif period == "утра" and target_hour == 12:
                target_hour = 0
            remaining = remaining[:m_time.start()] + remaining[m_time.end():]
            lower = remaining.lower()

    # === Time of day words ("утром", "вечером") ===
    if target_hour is None:
        for word, hour in _TIME_OF_DAY.items():
            if word in lower:
                target_hour = hour
                remaining = re.sub(re.escape(word), "", remaining, count=1, flags=re.IGNORECASE)
                lower = remaining.lower()
                break

    # === "завтра", "послезавтра" ===
    day_offset = 0
    if re.search(r"(?i)\bпослезавтра\b", lower):
        day_offset = 2
        remaining = re.sub(r"(?i)\bпослезавтра\b", "", remaining, count=1)
        lower = remaining.lower()
    elif re.search(r"(?i)\bзавтра\b", lower):
        day_offset = 1
        remaining = re.sub(r"(?i)\bзавтра\b", "", remaining, count=1)
        lower = remaining.lower()
    elif re.search(r"(?i)\bсегодня\b", lower):
        day_offset = 0
        remaining = re.sub(r"(?i)\bсегодня\b", "", remaining, count=1)
        lower = remaining.lower()

    # === Day of week ===
    weekday_target: int | None = None
    for name, wd in _WEEKDAYS.items():
        pat = re.compile(rf"(?i)\b(?:в\s+)?{re.escape(name)}\b")
        m_wd = pat.search(lower)
        if m_wd:
            weekday_target = wd
            remaining = remaining[:m_wd.start()] + remaining[m_wd.end():]
            lower = remaining.lower()
            break

    # === Build result ===
    has_date_marker = day_offset > 0 or weekday_target is not None
    has_time_marker = target_hour is not None

    if not has_date_marker and not has_time_marker and recurrence is None:
        # Нет временных маркеров
        return ParsedDateTime(dt=None, recurrence=None, confidence=0.0, remaining_text=original)

    if weekday_target is not None:
        # Ближайший день недели
        current_wd = now.weekday()
        days_ahead = (weekday_target - current_wd) % 7
        if days_ahead == 0:
            days_ahead = 7  # Следующая неделя
        target_date = now + timedelta(days=days_ahead)
    elif day_offset > 0:
        target_date = now + timedelta(days=day_offset)
    else:
        target_date = now

    if target_hour is not None:
        result_dt = target_date.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
        # Если время уже прошло сегодня и нет явного дня — переносим на завтра
        if result_dt <= now and not has_date_marker and weekday_target is None:
            result_dt += timedelta(days=1)
    elif recurrence is not None:
        # Recurrence без времени — ставим на 9:00
        result_dt = target_date.replace(hour=9, minute=0, second=0, microsecond=0)
        if result_dt <= now:
            result_dt += timedelta(days=1)
    else:
        # Дата без времени — ставим на 9:00
        result_dt = target_date.replace(hour=9, minute=0, second=0, microsecond=0)

    confidence = 0.85 if has_date_marker and has_time_marker else 0.7

    return ParsedDateTime(
        dt=_to_utc(result_dt),
        recurrence=recurrence,
        confidence=confidence,
        remaining_text=_clean_remaining(remaining),
    )


def _clean_remaining(text: str) -> str:
    """Очищает оставшийся текст от мусора."""
    # Убираем leading предлоги/частицы
    text = re.sub(r"^\s*(?:что\s+)?(?:нужно\s+)?(?:надо\s+)?", "", text.strip(), flags=re.IGNORECASE)
    # Убираем двойные пробелы
    text = re.sub(r"\s{2,}", " ", text).strip()
    # Убираем trailing запятые/точки
    text = text.strip(",.!? ")
    return text
