"""Встроенные tools: время, калькулятор, fetch URL, web search, погода, напоминания, задачи."""

from __future__ import annotations

import ast
import operator
from datetime import datetime, timezone

import aiohttp

from .registry import tool

# ---------- напоминания и задачи ----------


@tool(
    name="create_reminder",
    description="Создаёт напоминание на указанное время. Параметр description должен содержать время И текст, например: 'завтра в 9 утра позвонить маме', 'через 2 часа проверить почту'. Всегда используй этот инструмент когда пользователь просит напомнить или записать что-то.",
)
async def create_reminder(description: str, _user_id: str = "") -> str:
    """Создаёт напоминание через ReminderManager."""
    if not _user_id:
        return "error: нет user_id"
    try:
        from app.services.tasks import get_reminder_manager

        manager = get_reminder_manager()
        result = await manager.create_from_text(_user_id, description, tz_offset=3)
        scheduled = result.get("scheduled_at", "")
        title = result.get("title", description)
        rec = result.get("recurrence")
        rec_text = f" (повтор: {rec})" if rec else ""
        dt_str = ""
        if scheduled:
            try:
                from datetime import datetime as _dt

                dt = _dt.fromisoformat(str(scheduled).replace("Z", "+00:00"))
                dt_str = dt.strftime(" на %d.%m в %H:%M")
            except Exception:
                dt_str = f" на {scheduled}"
        return f"Напоминание создано{rec_text}: «{title}»{dt_str}"
    except ValueError as e:
        return f"Не смог разобрать время: {e}. Попробуй формат: 'завтра в 10:00 текст'"
    except Exception as exc:
        return f"error: {exc}"


@tool(
    name="create_task",
    description="Добавляет задачу в список дел пользователя. Используй когда пользователь говорит: запиши, добавь задачу, в блокнот, запомни что нужно сделать.",
)
async def create_task(title: str, _user_id: str = "") -> str:
    """Создаёт задачу."""
    if not _user_id:
        return "error: нет user_id"
    try:
        from app.services.tasks import get_reminder_manager

        manager = get_reminder_manager()
        result = await manager.create(_user_id, title)
        return f"Задача добавлена: «{result.get('title', title)}»"
    except Exception as exc:
        return f"error: {exc}"


@tool(
    name="list_reminders",
    description="Показывает список активных напоминаний и задач пользователя.",
)
async def list_reminders(_user_id: str = "") -> str:
    """Список напоминаний."""
    if not _user_id:
        return "error: нет user_id"
    try:
        from app.services.tasks import get_reminder_manager

        manager = get_reminder_manager()
        items = await manager.list(_user_id)
        if not items:
            return "Нет активных напоминаний."
        lines = []
        for r in items[:10]:
            title = r.get("title", "?")
            scheduled = r.get("scheduled_at", "")
            lines.append(f"• {title}" + (f" ({scheduled})" if scheduled else ""))
        return "\n".join(lines)
    except Exception as exc:
        return f"error: {exc}"

# ---------- безопасный калькулятор ----------

_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
    ast.FloorDiv: operator.floordiv,
}


def _eval(node: ast.AST) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, int | float):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.left), _eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.operand))
    raise ValueError(f"unsupported expression: {ast.dump(node)}")


@tool(name="calculator", description="Вычисляет арифметическое выражение (+,-,*,/,%,**, унарные).")
async def calculator(expression: str) -> str:
    """Возвращает результат вычисления выражения как строку."""
    try:
        tree = ast.parse(expression, mode="eval")
        result = _eval(tree.body)
        return str(result)
    except Exception as exc:
        return f"error: {exc}"


@tool(name="now", description="Возвращает текущие дату и время в ISO-8601 (UTC).")
async def now() -> str:
    return datetime.now(timezone.utc).isoformat()


@tool(name="fetch_url", description="Скачивает содержимое URL и возвращает первые 4000 символов.")
async def fetch_url(url: str) -> str:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=15) as resp:
                if resp.status != 200:
                    return f"http error {resp.status}"
                text = await resp.text()
                return text[:4000]
    except Exception as exc:
        return f"error: {exc}"


@tool(name="web_search", description="Поиск в DuckDuckGo, возвращает топ-результаты текстом.")
async def web_search(query: str, max_results: int = 5) -> str:
    try:
        from duckduckgo_search import DDGS

        with DDGS() as ddgs:
            hits = list(ddgs.text(query, max_results=max_results))
        if not hits:
            return "(no results)"
        return "\n\n".join(
            f"- {h.get('title', '')}\n  {h.get('href', '')}\n  {h.get('body', '')}"
            for h in hits
        )
    except Exception as exc:
        return f"error: {exc}"


@tool(
    name="weather",
    description="Возвращает текущую погоду в указанном городе (через OpenWeatherMap). Принимает русское или английское название города.",
)
async def weather(city: str) -> str:
    """Текущая погода: температура, ощущается, влажность, описание, ветер."""
    try:
        from app.services.weather import WeatherService

        result = await WeatherService().get(city)
        if not result:
            return f"Не получилось узнать погоду для «{city}» (нужен OPENWEATHER_API_KEY)."
        parts = [
            f"Погода в {result.get('city', city)}:",
            f"- Температура: {result.get('temperature')}°C (ощущается {result.get('feels_like')}°C)",
            f"- Описание: {result.get('description', '—')}",
            f"- Влажность: {result.get('humidity')}%",
            f"- Ветер: {result.get('wind_speed')} м/с",
        ]
        return "\n".join(parts)
    except Exception as exc:
        return f"weather error: {exc}"


@tool(
    name="github_repo_info",
    description="Возвращает базовую информацию о GitHub-репозитории (stars, открытые issue, последний коммит).",
)
async def github_repo_info(owner: str, repo: str) -> str:
    """Лёгкая обёртка над GitHub REST API."""
    try:
        import os

        headers = {"Accept": "application/vnd.github+json"}
        token = os.environ.get("GITHUB_TOKEN", "")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"https://api.github.com/repos/{owner}/{repo}",
                headers=headers,
                timeout=15,
            ) as resp:
                if resp.status != 200:
                    return f"github error {resp.status}"
                data = await resp.json()
        return (
            f"{data.get('full_name')}\n"
            f"⭐ {data.get('stargazers_count', 0)} · "
            f"🐛 {data.get('open_issues_count', 0)} open issues · "
            f"🔧 {data.get('language', '?')}\n"
            f"{data.get('description', '')}\n"
            f"Updated: {data.get('updated_at', '')}"
        )
    except Exception as exc:
        return f"github error: {exc}"
