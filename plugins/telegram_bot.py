"""Telegram Bot интеграция для Фреди.

Sprint 9: Фреди доступен как Telegram-бот — второй канал общения.
Пользователь может писать Фреди в Telegram, получать уведомления.

Настройка: TELEGRAM_BOT_TOKEN в .env
Запуск: автоматически при загрузке плагина.

Использование:
  - Любое сообщение → chat с Фреди (через LLM)
  - /remind <text> → создаёт напоминание
  - /goals → показывает активные цели
  - /habits → показывает привычки
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

# Lazy imports — плагин не должен ломать старт если нет зависимостей
_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")

if _BOT_TOKEN:
    import aiohttp

    from app.core.logging import get_logger
    from app.services.tools import tool

    logger = get_logger(__name__)

    TELEGRAM_API = f"https://api.telegram.org/bot{_BOT_TOKEN}"

    # Маппинг telegram user_id → freddy user_id (простой in-memory)
    _user_map: dict[int, str] = {}

    @tool(name="telegram_send", description="Отправить сообщение пользователю в Telegram.")
    async def telegram_send(chat_id: str, text: str) -> str:
        """Отправляет сообщение в Telegram чат."""
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{TELEGRAM_API}/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
                timeout=10,
            ) as resp:
                if resp.status == 200:
                    return "sent"
                body = await resp.text()
                return f"error: {resp.status} {body[:200]}"

    @tool(name="telegram_get_updates", description="Получить последние сообщения из Telegram.")
    async def telegram_get_updates(offset: int = 0) -> str:
        """Получает новые сообщения через long polling."""
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{TELEGRAM_API}/getUpdates",
                params={"offset": offset, "timeout": 5, "limit": 10},
                timeout=15,
            ) as resp:
                if resp.status != 200:
                    return "error"
                data = await resp.json()
                updates = data.get("result", [])
                return json.dumps(
                    [
                        {
                            "id": u["update_id"],
                            "chat_id": u.get("message", {}).get("chat", {}).get("id"),
                            "text": u.get("message", {}).get("text", ""),
                            "from": u.get("message", {}).get("from", {}).get("first_name", ""),
                        }
                        for u in updates
                        if "message" in u
                    ],
                    ensure_ascii=False,
                )

    async def _process_telegram_message(chat_id: int, text: str, username: str) -> str:
        """Обрабатывает входящее сообщение из Telegram."""
        from app.services.llm import ChatMessage, default_router

        # Определяем user_id
        user_id = _user_map.get(chat_id, f"tg_{chat_id}")

        # Обработка команд
        if text.startswith("/remind "):
            from app.services.tasks import get_reminder_manager

            payload = text[8:].strip()
            try:
                mgr = get_reminder_manager()
                result = await mgr.create_from_text(user_id, payload)
                return f"Напомню: «{result['title']}»"
            except Exception:
                return f"Не смог разобрать: {payload}"

        if text in ("/goals", "/цели"):
            from app.db import GoalRepository, session_scope

            async with session_scope() as session:
                goals = await GoalRepository(session).list_active(user_id)
            if not goals:
                return "Нет активных целей."
            return "\n".join(f"• {g.title} ({g.progress_pct}%)" for g in goals[:10])

        if text in ("/habits", "/привычки"):
            from app.db import HabitRepository, session_scope

            async with session_scope() as session:
                habits = await HabitRepository(session).list(user_id)
            if not habits:
                return "Нет привычек."
            return "\n".join(f"{'🔥' if h.streak > 0 else '💤'} {h.title} (streak: {h.streak})" for h in habits[:10])

        # Обычное сообщение → LLM
        messages = [
            ChatMessage(role="system", content="Ты Фреди — AI-ассистент. Отвечай кратко (1-3 предложения). Это Telegram-чат."),
            ChatMessage(role="user", content=text),
        ]
        try:
            resp = await default_router().chat(messages, profile="fast", max_tokens=300)  # type: ignore
            return resp.text
        except Exception as exc:
            return f"Ошибка: {exc}"

    async def start_polling() -> None:
        """Запускает long-polling для Telegram (фоновая задача)."""
        logger.info("🤖 Telegram bot polling started")
        offset = 0
        while True:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        f"{TELEGRAM_API}/getUpdates",
                        params={"offset": offset, "timeout": 30, "limit": 10},
                        timeout=35,
                    ) as resp:
                        if resp.status != 200:
                            await asyncio.sleep(5)
                            continue
                        data = await resp.json()

                for update in data.get("result", []):
                    offset = update["update_id"] + 1
                    msg = update.get("message")
                    if not msg or not msg.get("text"):
                        continue
                    chat_id = msg["chat"]["id"]
                    text = msg["text"]
                    username = msg.get("from", {}).get("first_name", "")

                    try:
                        reply = await _process_telegram_message(chat_id, text, username)
                        await telegram_send(str(chat_id), reply)
                    except Exception as exc:
                        logger.warning("Telegram message handling failed: %s", exc)

            except Exception as exc:
                logger.debug("Telegram polling error: %s", exc)
                await asyncio.sleep(5)

    # Auto-start polling in background
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(start_polling())
        else:
            logger.debug("Telegram polling deferred — event loop not running")
    except RuntimeError:
        pass
