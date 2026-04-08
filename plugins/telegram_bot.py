"""Telegram Bot интеграция для Фреди.

Sprint 9 + voice upgrade: Фреди как Telegram-бот — второй канал общения.

Функции:
  - Текст в обе стороны (chat ↔ LLM)
  - **Голос в обе стороны** (voice → STT → LLM → TTS → voice reply)
  - Команды: /remind, /goals, /habits
  - Напоминания из scheduler автоматически пушатся в Telegram для
    пользователей, которые пришли через Telegram (user_id начинается с "tg_")

Настройка: `TELEGRAM_TOKEN` или `TELEGRAM_BOT_TOKEN` в .env (принимаются оба
варианта — на Render мы их по-разному назвали).
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

# Lazy imports — плагин не должен ломать старт если нет зависимостей.
# Принимаем оба имени переменной окружения: так мы не падаем, если
# на Render задан TELEGRAM_TOKEN, а код раньше читал TELEGRAM_BOT_TOKEN.
_BOT_TOKEN = (
    os.environ.get("TELEGRAM_BOT_TOKEN")
    or os.environ.get("TELEGRAM_TOKEN")
    or ""
).strip()

if _BOT_TOKEN:
    import aiohttp

    from app.core.logging import get_logger
    from app.services.tools import tool

    logger = get_logger(__name__)

    TELEGRAM_API = f"https://api.telegram.org/bot{_BOT_TOKEN}"
    TELEGRAM_FILE = f"https://api.telegram.org/file/bot{_BOT_TOKEN}"

    # Маппинг telegram user_id → freddy user_id (простой in-memory)
    _user_map: dict[int, str] = {}

    # ---------- low-level Telegram helpers ----------

    @tool(name="telegram_send", description="Отправить текстовое сообщение пользователю в Telegram.")
    async def telegram_send(chat_id: str, text: str) -> str:
        """Отправляет текстовое сообщение в Telegram чат."""
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{TELEGRAM_API}/sendMessage",
                json={"chat_id": chat_id, "text": text[:4000], "parse_mode": "Markdown"},
                timeout=10,
            ) as resp:
                if resp.status == 200:
                    return "sent"
                body = await resp.text()
                return f"error: {resp.status} {body[:200]}"

    @tool(name="telegram_send_voice", description="Отправить голосовое сообщение пользователю в Telegram.")
    async def telegram_send_voice(
        chat_id: str, ogg_bytes: bytes, caption: str | None = None
    ) -> str:
        """Отправляет голосовое сообщение (OGG Opus) через sendVoice."""
        if not ogg_bytes:
            return "error: empty audio"
        form = aiohttp.FormData()
        form.add_field("chat_id", str(chat_id))
        if caption:
            form.add_field("caption", caption[:1000])
        form.add_field(
            "voice",
            ogg_bytes,
            filename="freddy.ogg",
            content_type="audio/ogg",
        )
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{TELEGRAM_API}/sendVoice", data=form, timeout=30
            ) as resp:
                if resp.status == 200:
                    return "sent"
                body = await resp.text()
                return f"error: {resp.status} {body[:200]}"

    async def _download_voice(file_id: str) -> bytes | None:
        """Скачивает аудио-файл голосового сообщения по file_id."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{TELEGRAM_API}/getFile",
                    params={"file_id": file_id},
                    timeout=10,
                ) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()
                file_path = data.get("result", {}).get("file_path")
                if not file_path:
                    return None
                async with session.get(
                    f"{TELEGRAM_FILE}/{file_path}", timeout=30
                ) as resp:
                    if resp.status != 200:
                        return None
                    return await resp.read()
        except Exception as exc:  # pragma: no cover
            logger.warning("Telegram voice download failed: %s", exc)
            return None

    @tool(name="telegram_get_updates", description="Получить последние сообщения из Telegram.")
    async def telegram_get_updates(offset: int = 0) -> str:
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

    # ---------- message processing ----------

    async def _process_telegram_message(chat_id: int, text: str, username: str) -> str:
        """Обрабатывает текст сообщения из Telegram и возвращает ответ."""
        from app.services.llm import ChatMessage, default_router

        user_id = _user_map.get(chat_id, f"tg_{chat_id}")

        # Обработка команд
        if text.startswith("/start"):
            return (
                "Привет! Я Фреди — твой AI-ассистент.\n\n"
                "Пиши мне текстом или отправляй голосовые сообщения. "
                "Я отвечу так же.\n\n"
                "Команды:\n"
                "• /remind <текст> — напоминание\n"
                "• /goals — активные цели\n"
                "• /habits — привычки"
            )

        if text.startswith("/remind "):
            from app.services.tasks import get_reminder_manager

            payload = text[8:].strip()
            try:
                mgr = get_reminder_manager()
                result = await mgr.create_from_text(user_id, payload)
                return f"Напомню: «{result['title']}» — {result.get('scheduled_at','скоро')}"
            except Exception:
                return f"Не смог разобрать: {payload}"

        if text in ("/goals", "/цели"):
            from app.db import GoalRepository, session_scope

            async with session_scope() as session:
                goals = await GoalRepository(session).list_active(user_id)
            if not goals:
                return "Нет активных целей. Создай цель командой в веб-интерфейсе или напиши «моя цель — …»."
            return "\n".join(f"• {g.title} ({g.progress_pct}%)" for g in goals[:10])

        if text in ("/habits", "/привычки"):
            from app.db import HabitRepository, session_scope

            async with session_scope() as session:
                habits = await HabitRepository(session).list(user_id)
            if not habits:
                return "Нет привычек. Создай через «новая привычка — …» в веб-интерфейсе."
            return "\n".join(
                f"{'🔥' if h.streak > 0 else '💤'} {h.title} (streak: {h.streak})"
                for h in habits[:10]
            )

        # Обычное сообщение → LLM
        messages = [
            ChatMessage(
                role="system",
                content=(
                    "Ты Фреди — тёплый AI-ассистент в Telegram. "
                    "Отвечай кратко (1-3 предложения), по-русски, на «ты»."
                ),
            ),
            ChatMessage(role="user", content=text),
        ]
        try:
            resp = await default_router().chat(messages, profile="fast", max_tokens=300)  # type: ignore
            return resp.text
        except Exception as exc:
            return f"Ошибка: {exc}"

    async def _handle_voice_message(
        chat_id: int, file_id: str, username: str
    ) -> tuple[str, bytes | None]:
        """Обрабатывает голосовое сообщение: STT → LLM → TTS.

        Возвращает (текст ответа, ogg-байты для sendVoice). Если TTS
        недоступен — ogg будет None, отправим только текст.
        """
        from app.services.voice import VoiceService

        audio = await _download_voice(file_id)
        if audio is None:
            return ("Не смог скачать голосовое сообщение.", None)

        voice_svc = VoiceService()
        transcript, provider = await voice_svc.transcribe(
            audio, content_type="audio/ogg", language="ru"
        )
        if not transcript:
            return (
                "Не удалось распознать голос. Попробуй написать текстом.",
                None,
            )

        logger.info(
            "🎙️ telegram voice (%s) from %s: %s",
            provider, username, transcript[:100]
        )

        reply_text = await _process_telegram_message(chat_id, transcript, username)

        # TTS → OGG Opus (Telegram sendVoice требует именно этот формат)
        tts_audio, tts_provider = await voice_svc.synthesize(
            reply_text, voice="madirus", tone="warm", prefer="yandex"
        )
        if tts_audio:
            logger.info("🔊 telegram voice reply via %s", tts_provider)
        return (reply_text, tts_audio)

    # ---------- polling loop ----------

    async def start_polling() -> None:
        """Запускает long-polling для Telegram (фоновая задача)."""
        logger.info("🤖 Telegram bot polling started (accepts voice)")
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
                    if not msg:
                        continue

                    chat_id = msg["chat"]["id"]
                    username = msg.get("from", {}).get("first_name", "")

                    try:
                        # Голосовое сообщение имеет больший приоритет
                        if msg.get("voice"):
                            file_id = msg["voice"].get("file_id", "")
                            if not file_id:
                                continue
                            reply_text, voice_bytes = await _handle_voice_message(
                                chat_id, file_id, username
                            )
                            # Если удалось синтезировать — шлём голосом + текст как caption
                            if voice_bytes:
                                await telegram_send_voice(
                                    str(chat_id), voice_bytes, caption=reply_text[:900]
                                )
                            else:
                                await telegram_send(str(chat_id), reply_text)

                        # Обычный текст
                        elif msg.get("text"):
                            text = msg["text"]
                            reply = await _process_telegram_message(
                                chat_id, text, username
                            )
                            await telegram_send(str(chat_id), reply)

                    except Exception as exc:
                        logger.warning(
                            "Telegram message handling failed: %s", exc
                        )

            except Exception as exc:
                logger.debug("Telegram polling error: %s", exc)
                await asyncio.sleep(5)

    # ---------- exports used by other modules ----------

    async def notify_user(chat_id: int | str, text: str) -> bool:
        """Публичный хелпер: послать напоминание/уведомление конкретному TG-чату.

        Используется ReminderManager для пуша напоминаний в Telegram.
        """
        result = await telegram_send(str(chat_id), text)
        return result == "sent"

    def is_configured() -> bool:
        return bool(_BOT_TOKEN)

    # Auto-start polling in background
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(start_polling())
        else:
            logger.debug("Telegram polling deferred — event loop not running")
    except RuntimeError:
        pass

else:
    # Плагин не настроен — экспортируем заглушки чтобы импорты не падали.
    def is_configured() -> bool:  # type: ignore[misc]
        return False

    async def notify_user(chat_id, text: str) -> bool:  # type: ignore[misc]  # noqa: ARG001
        return False
