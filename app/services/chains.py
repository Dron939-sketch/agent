"""Автономное выполнение цепочек действий.

Sprint Jarvis: Фреди самостоятельно составляет план из нескольких шагов
и выполняет их последовательно, запрашивая подтверждение перед
необратимыми действиями.

Пример:
  User: "Организуй встречу с Аней в пятницу"
  Freddy: [plan] 1. Проверить календарь на пятницу
                 2. Найти свободный слот
                 3. Создать событие
                 4. Отправить приглашение
          → Выполняет шаги 1-2 автоматически
          → Просит подтверждение для 3-4
"""

from __future__ import annotations

import json
from typing import Any

from app.core.logging import get_logger
from app.services.llm import ChatMessage, default_router

logger = get_logger(__name__)

PLAN_SYSTEM_PROMPT = """\
Ты Фреди — автономный AI-ассистент. Пользователь просит выполнить задачу.

Составь план действий в формате JSON:
{
  "task": "краткое описание задачи",
  "steps": [
    {"action": "описание шага", "tool": "имя_tool или null", "args": {}, "needs_confirmation": false},
    ...
  ],
  "confirmation_message": "Что сказать пользователю перед выполнением (кратко)"
}

Правила:
- Разбей задачу на 2-5 конкретных шагов
- needs_confirmation=true для: отправки сообщений, создания событий, удаления данных
- needs_confirmation=false для: чтения данных, поиска, проверки статусов
- tool: имя зарегистрированного tool (calendar_today, email_send, hass_turn_on, etc.) или null
- Если задача простая (1 шаг) — всё равно оформи как план
- confirmation_message — кратко опиши план пользователю
- СТРОГО JSON без markdown-обёрток
"""


async def plan_chain(
    user_message: str,
    *,
    context: str = "",
) -> dict[str, Any] | None:
    """Составляет план выполнения задачи.

    Returns dict с task, steps, confirmation_message — или None если задача
    не требует цепочки действий.
    """
    messages = [
        ChatMessage(role="system", content=PLAN_SYSTEM_PROMPT),
        ChatMessage(role="user", content=f"Контекст: {context}\n\nЗадача: {user_message}" if context else user_message),
    ]

    try:
        resp = await default_router().chat(messages, profile="smart", temperature=0.2, max_tokens=800)  # type: ignore
        text = resp.text.strip()

        # Extract JSON
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1:
            return None
        plan = json.loads(text[start:end + 1])

        if not plan.get("steps"):
            return None

        return plan
    except Exception as exc:
        logger.warning("plan_chain failed: %s", exc)
        return None


async def execute_step(
    step: dict[str, Any],
) -> dict[str, Any]:
    """Выполняет один шаг плана.

    Returns dict с result и status (done/error/skipped).
    """
    tool_name = step.get("tool")
    if not tool_name:
        return {"status": "skipped", "result": step.get("action", "no-op")}

    try:
        from app.services.tools.registry import default_registry

        registry = default_registry()
        if tool_name not in registry:
            return {"status": "error", "result": f"Tool '{tool_name}' не найден"}

        args = step.get("args", {})
        result = await registry.call(tool_name, **args)
        return {"status": "done", "result": str(result)[:500]}
    except Exception as exc:
        return {"status": "error", "result": str(exc)[:200]}


async def execute_chain(
    plan: dict[str, Any],
    *,
    auto_confirm: bool = False,
) -> list[dict[str, Any]]:
    """Выполняет план. Останавливается на шаге с needs_confirmation=True.

    Returns список результатов выполненных шагов.
    При auto_confirm=True — выполняет все шаги без остановки.
    """
    results: list[dict[str, Any]] = []

    for i, step in enumerate(plan.get("steps", [])):
        if step.get("needs_confirmation") and not auto_confirm:
            results.append({
                "step": i + 1,
                "action": step["action"],
                "status": "awaiting_confirmation",
                "result": "Требуется подтверждение",
            })
            break

        step_result = await execute_step(step)
        results.append({
            "step": i + 1,
            "action": step.get("action", ""),
            **step_result,
        })

        if step_result["status"] == "error":
            break  # Останавливаемся на ошибке

    return results


def format_chain_response(
    plan: dict[str, Any],
    results: list[dict[str, Any]],
) -> str:
    """Форматирует результат выполнения цепочки для пользователя."""
    lines: list[str] = []

    if plan.get("confirmation_message"):
        lines.append(plan["confirmation_message"])
        lines.append("")

    for r in results:
        status_icon = {
            "done": "✅",
            "error": "❌",
            "skipped": "⏭",
            "awaiting_confirmation": "⏳",
        }.get(r["status"], "•")

        lines.append(f"{status_icon} Шаг {r['step']}: {r['action']}")
        if r["status"] == "done" and r.get("result"):
            lines.append(f"   → {r['result'][:100]}")
        elif r["status"] == "error":
            lines.append(f"   → Ошибка: {r['result'][:100]}")
        elif r["status"] == "awaiting_confirmation":
            lines.append("   → Подтверди, чтобы продолжить.")

    has_pending = any(r["status"] == "awaiting_confirmation" for r in results)
    if has_pending:
        lines.append("")
        lines.append("Продолжить? (да/нет)")

    return "\n".join(lines)


def is_chain_request(text: str) -> bool:
    """Эвристика: нужна ли цепочка действий для этого запроса."""
    import re

    # Мультишаговые паттерны
    chain_patterns = [
        re.compile(r"(?i)организуй", re.I),
        re.compile(r"(?i)настрой", re.I),
        re.compile(r"(?i)подготовь", re.I),
        re.compile(r"(?i)составь план", re.I),
        re.compile(r"(?i)сделай.*и.*и", re.I),  # "сделай X и Y и Z"
        re.compile(r"(?i)создай.*отправь", re.I),
        re.compile(r"(?i)проверь.*и\s+(если|потом|затем)", re.I),
        re.compile(r"(?i)автоматически", re.I),
    ]
    return any(p.search(text) for p in chain_patterns)
