"""Freddy SDK — sync + async клиенты.

Sync-клиент (Freddy) — для скриптов, ботов, простых интеграций.
Async-клиент (AsyncFreddy) — для FastAPI, aiohttp, asyncio-проектов.

Оба клиента предоставляют одинаковый API.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

try:
    import aiohttp
except ImportError:
    aiohttp = None  # type: ignore

try:
    import requests as _requests
except ImportError:
    _requests = None  # type: ignore


class FreddyError(Exception):
    """Ошибка Freddy API."""

    def __init__(self, status: int, message: str) -> None:
        self.status = status
        super().__init__(f"[{status}] {message}")


# ============================================================
#  Async Client
# ============================================================


class AsyncFreddy:
    """Асинхронный клиент Freddy API.

    Использование:
        async with AsyncFreddy("https://agent-ynlg.onrender.com") as f:
            await f.login("user", "pass")
            reply = await f.chat("Привет!")
    """

    def __init__(
        self,
        url: str = "http://localhost:8000",
        token: str | None = None,
    ) -> None:
        self.url = url.rstrip("/")
        self.token = token
        self._session: aiohttp.ClientSession | None = None

    async def __aenter__(self) -> "AsyncFreddy":
        if aiohttp is None:
            raise ImportError("pip install aiohttp")
        self._session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._session:
            await self._session.close()
            self._session = None

    def _headers(self) -> dict[str, str]:
        h: dict[str, str] = {"Content-Type": "application/json"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            if aiohttp is None:
                raise ImportError("pip install aiohttp")
            self._session = aiohttp.ClientSession()
        return self._session

    async def _post(self, path: str, data: dict | None = None, **kwargs: Any) -> dict:
        session = await self._ensure_session()
        async with session.post(
            f"{self.url}{path}",
            json=data,
            headers=self._headers(),
            timeout=aiohttp.ClientTimeout(total=60),
            **kwargs,
        ) as resp:
            if resp.status >= 400:
                body = await resp.text()
                raise FreddyError(resp.status, body[:500])
            return await resp.json()

    async def _post_form(self, path: str, form: aiohttp.FormData) -> dict:
        session = await self._ensure_session()
        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        async with session.post(
            f"{self.url}{path}",
            data=form,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=60),
        ) as resp:
            if resp.status >= 400:
                body = await resp.text()
                raise FreddyError(resp.status, body[:500])
            return await resp.json()

    async def _post_bytes(self, path: str, data: dict) -> bytes:
        session = await self._ensure_session()
        async with session.post(
            f"{self.url}{path}",
            json=data,
            headers=self._headers(),
            timeout=aiohttp.ClientTimeout(total=60),
        ) as resp:
            if resp.status >= 400:
                body = await resp.text()
                raise FreddyError(resp.status, body[:500])
            return await resp.read()

    async def _get(self, path: str) -> dict:
        session = await self._ensure_session()
        async with session.get(
            f"{self.url}{path}",
            headers=self._headers(),
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            if resp.status >= 400:
                body = await resp.text()
                raise FreddyError(resp.status, body[:500])
            return await resp.json()

    # --- Auth ---

    async def login(self, username: str, password: str) -> str:
        """Логин. Возвращает и сохраняет токен."""
        data = await self._post("/api/auth/login", {"username": username, "password": password})
        self.token = data["access_token"]
        return self.token

    async def register(self, username: str, email: str, password: str) -> str:
        """Регистрация + автологин."""
        await self._post("/api/auth/register", {
            "username": username, "email": email, "password": password,
        })
        return await self.login(username, password)

    # --- Chat ---

    async def chat(
        self,
        message: str,
        *,
        profile: str = "smart",
        use_memory: bool = True,
    ) -> dict[str, Any]:
        """Отправляет сообщение, получает умный ответ.

        Returns: {"reply": str, "model": str, "emotion": str, ...}
        """
        return await self._post("/api/chat/", {
            "message": message,
            "profile": profile,
            "use_memory": use_memory,
        })

    async def chat_text(self, message: str) -> str:
        """Упрощённый вариант — только текст ответа."""
        data = await self.chat(message)
        return data.get("reply", "")

    # --- Voice / TTS ---

    async def speak(
        self,
        text: str,
        *,
        voice: str = "jarvis",
        tone: str = "warm",
    ) -> bytes:
        """Текст → аудио (голос Джарвиса). Возвращает audio bytes."""
        return await self._post_bytes("/api/voice/tts/stream", {
            "text": text, "voice": voice, "tone": tone,
        })

    async def speak_to_file(
        self,
        text: str,
        path: str = "output.ogg",
        *,
        voice: str = "jarvis",
        tone: str = "warm",
    ) -> str:
        """Текст → аудио файл. Возвращает путь к файлу."""
        audio = await self.speak(text, voice=voice, tone=tone)
        Path(path).write_bytes(audio)
        return path

    async def transcribe(self, audio_path: str) -> dict[str, str]:
        """Аудио файл → текст (STT).

        Returns: {"text": str, "provider": str}
        """
        form = aiohttp.FormData()
        form.add_field(
            "audio",
            open(audio_path, "rb"),
            filename="voice.webm",
            content_type="audio/webm",
        )
        return await self._post_form("/api/voice/stt", form)

    async def voice_loop(self, audio_path: str) -> dict[str, Any]:
        """Полный голосовой цикл: аудио → STT → LLM → ответ.

        Returns: {"transcript": str, "reply": str, "reply_model": str, ...}
        """
        form = aiohttp.FormData()
        form.add_field(
            "audio",
            open(audio_path, "rb"),
            filename="voice.webm",
            content_type="audio/webm",
        )
        return await self._post_form("/api/voice/full-loop", form)

    # --- Reminders ---

    async def remind(self, text: str, tz_offset: int = 3) -> dict[str, Any]:
        """Создаёт напоминание из текста.

        Примеры: "через 2 часа позвонить", "завтра в 9 утра отчёт"
        Returns: {"task_id": int, "title": str, "scheduled_at": str}
        """
        return await self._post("/api/reminders", {"text": text, "tz_offset": tz_offset})

    async def list_reminders(self) -> list[dict[str, Any]]:
        """Список активных напоминаний."""
        data = await self._get("/api/reminders")
        return data.get("reminders", [])

    # --- Goals & Habits ---

    async def set_goal(self, title: str) -> dict:
        """Создаёт цель."""
        return await self._post("/api/coach/goals", {"title": title})

    async def list_goals(self) -> list[dict]:
        """Список целей."""
        data = await self._get("/api/coach/goals")
        return data if isinstance(data, list) else data.get("goals", [])

    async def list_habits(self) -> list[dict]:
        """Список привычек."""
        data = await self._get("/api/coach/habits")
        return data if isinstance(data, list) else data.get("habits", [])

    # --- Utility ---

    async def ping(self) -> bool:
        """Проверяет доступность сервера."""
        try:
            session = await self._ensure_session()
            async with session.get(f"{self.url}/health", timeout=aiohttp.ClientTimeout(total=5)) as resp:
                return resp.status == 200
        except Exception:
            return False

    async def voices(self) -> list[dict]:
        """Список доступных голосов."""
        return await self._get("/api/voice/voices")

    async def close(self) -> None:
        """Закрывает соединение."""
        if self._session:
            await self._session.close()
            self._session = None


# ============================================================
#  Sync Client (обёртка над AsyncFreddy)
# ============================================================


class Freddy:
    """Синхронный клиент Freddy API.

    Использование:
        f = Freddy("https://agent-ynlg.onrender.com")
        f.login("user", "pass")
        reply = f.chat("Привет!")
        audio = f.speak("Добрый вечер, сэр")
    """

    def __init__(
        self,
        url: str = "http://localhost:8000",
        token: str | None = None,
    ) -> None:
        self._async = AsyncFreddy(url=url, token=token)
        self._loop: asyncio.AbstractEventLoop | None = None

    def _run(self, coro: Any) -> Any:
        """Запускает async корутину синхронно."""
        try:
            loop = asyncio.get_running_loop()
            # Мы внутри async context — нельзя использовать run()
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, coro).result()
        except RuntimeError:
            return asyncio.run(coro)

    @property
    def token(self) -> str | None:
        return self._async.token

    @token.setter
    def token(self, value: str | None) -> None:
        self._async.token = value

    def login(self, username: str, password: str) -> str:
        return self._run(self._async.login(username, password))

    def register(self, username: str, email: str, password: str) -> str:
        return self._run(self._async.register(username, email, password))

    def chat(self, message: str, **kwargs: Any) -> dict[str, Any]:
        return self._run(self._async.chat(message, **kwargs))

    def chat_text(self, message: str) -> str:
        return self._run(self._async.chat_text(message))

    def speak(self, text: str, **kwargs: Any) -> bytes:
        return self._run(self._async.speak(text, **kwargs))

    def speak_to_file(self, text: str, path: str = "output.ogg", **kwargs: Any) -> str:
        return self._run(self._async.speak_to_file(text, path, **kwargs))

    def transcribe(self, audio_path: str) -> dict[str, str]:
        return self._run(self._async.transcribe(audio_path))

    def voice_loop(self, audio_path: str) -> dict[str, Any]:
        return self._run(self._async.voice_loop(audio_path))

    def remind(self, text: str, tz_offset: int = 3) -> dict[str, Any]:
        return self._run(self._async.remind(text, tz_offset=tz_offset))

    def list_reminders(self) -> list[dict[str, Any]]:
        return self._run(self._async.list_reminders())

    def set_goal(self, title: str) -> dict:
        return self._run(self._async.set_goal(title))

    def list_goals(self) -> list[dict]:
        return self._run(self._async.list_goals())

    def list_habits(self) -> list[dict]:
        return self._run(self._async.list_habits())

    def ping(self) -> bool:
        return self._run(self._async.ping())

    def voices(self) -> list[dict]:
        return self._run(self._async.voices())

    def close(self) -> None:
        self._run(self._async.close())
