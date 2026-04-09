"""
Freddy Service для Frederick — подключает умную говорилку для пользователей без теста.

Этот файл копируется в Frederick: backend/services/freddy_service.py

Использование в Frederick main.py:
    from services.freddy_service import FreddyService

    freddy = FreddyService()
    response = await freddy.chat(user_id, message, history=history)
    audio = await freddy.speak(response["reply"])
"""

import os
import logging
import aiohttp
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

# Конфигурация из .env
FREDDY_URL = os.environ.get("FREDDY_URL", "https://agent-ynlg.onrender.com")
FREDDY_USERNAME = os.environ.get("FREDDY_USERNAME", "")
FREDDY_PASSWORD = os.environ.get("FREDDY_PASSWORD", "")
FREDDY_TOKEN = os.environ.get("FREDDY_TOKEN", "")


class FreddyService:
    """Сервис подключения к Freddy AI Assistant.

    Для пользователей Frederick, которые ещё не прошли тест —
    вместо простого BasicMode используем полноценного Фреди с памятью,
    эмоциями, голосом Джарвиса и умным контекстом.
    """

    def __init__(self):
        self.url = FREDDY_URL.rstrip("/")
        self.token = FREDDY_TOKEN
        self._session: Optional[aiohttp.ClientSession] = None
        self._logged_in = False
        logger.info(f"FreddyService: url={self.url}, token={'✅' if self.token else '❌'}")

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def _ensure_auth(self) -> bool:
        """Логинится если нет токена."""
        if self.token:
            return True
        if not FREDDY_USERNAME or not FREDDY_PASSWORD:
            logger.warning("FreddyService: нет credentials (FREDDY_TOKEN или FREDDY_USERNAME+PASSWORD)")
            return False
        if self._logged_in:
            return True

        try:
            session = await self._get_session()
            async with session.post(
                f"{self.url}/api/auth/login",
                json={"username": FREDDY_USERNAME, "password": FREDDY_PASSWORD},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self.token = data.get("access_token", "")
                    self._logged_in = True
                    logger.info("FreddyService: авторизация успешна")
                    return True
                else:
                    body = await resp.text()
                    logger.error(f"FreddyService login failed: {resp.status} {body[:200]}")
                    return False
        except Exception as exc:
            logger.error(f"FreddyService login error: {exc}")
            return False

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    # === Основные методы ===

    async def chat(
        self,
        user_id: int,
        message: str,
        *,
        history: Optional[List[Dict]] = None,
        profile: str = "smart",
    ) -> Dict[str, Any]:
        """Отправляет сообщение Фреди, получает умный ответ.

        Args:
            user_id: ID пользователя в Frederick
            message: текст сообщения
            history: история диалога (опционально)
            profile: профиль LLM (smart/fast/cheap)

        Returns:
            {"reply": str, "model": str, "emotion": str, "tone": str}
        """
        if not await self._ensure_auth():
            return {"reply": "", "model": "unavailable", "error": "auth_failed"}

        try:
            session = await self._get_session()
            async with session.post(
                f"{self.url}/api/chat/",
                json={
                    "message": message,
                    "profile": profile,
                    "use_memory": True,
                },
                headers=self._headers(),
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    logger.info(f"FreddyService: reply from {data.get('model','?')}, {len(data.get('reply',''))} chars")
                    return data
                else:
                    body = await resp.text()
                    logger.error(f"FreddyService chat error: {resp.status} {body[:200]}")
                    # Retry auth если 401
                    if resp.status == 401:
                        self.token = ""
                        self._logged_in = False
                    return {"reply": "", "model": "error", "error": body[:200]}
        except Exception as exc:
            logger.error(f"FreddyService chat exception: {exc}")
            return {"reply": "", "model": "error", "error": str(exc)}

    async def speak(
        self,
        text: str,
        *,
        voice: str = "jarvis",
        tone: str = "warm",
    ) -> Optional[bytes]:
        """Озвучивает текст голосом Джарвиса.

        Returns: audio bytes (OGG/MP3) или None
        """
        if not await self._ensure_auth():
            return None

        try:
            session = await self._get_session()
            async with session.post(
                f"{self.url}/api/voice/tts/stream",
                json={"text": text[:1000], "voice": voice, "tone": tone},
                headers=self._headers(),
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status == 200:
                    audio = await resp.read()
                    logger.info(f"FreddyService: TTS {len(audio)} bytes")
                    return audio
                else:
                    logger.error(f"FreddyService TTS error: {resp.status}")
                    return None
        except Exception as exc:
            logger.error(f"FreddyService TTS exception: {exc}")
            return None

    async def remind(self, user_id: int, text: str) -> Dict[str, Any]:
        """Создаёт напоминание через Фреди."""
        if not await self._ensure_auth():
            return {"error": "auth_failed"}

        try:
            session = await self._get_session()
            async with session.post(
                f"{self.url}/api/reminders",
                json={"text": text, "tz_offset": 3},
                headers=self._headers(),
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status in (200, 201):
                    return await resp.json()
                return {"error": f"status {resp.status}"}
        except Exception as exc:
            return {"error": str(exc)}

    async def is_available(self) -> bool:
        """Проверяет доступность Freddy API."""
        try:
            session = await self._get_session()
            async with session.get(
                f"{self.url}/health",
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                return resp.status == 200
        except Exception:
            return False

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()


# === Singleton ===
_instance: Optional[FreddyService] = None


def get_freddy_service() -> FreddyService:
    global _instance
    if _instance is None:
        _instance = FreddyService()
    return _instance
