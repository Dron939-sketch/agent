"""Spotify интеграция — управление музыкой.

Настройка в .env:
  SPOTIFY_CLIENT_ID=...
  SPOTIFY_CLIENT_SECRET=...
  SPOTIFY_REFRESH_TOKEN=...

Получить refresh token: https://developer.spotify.com/documentation/web-api/tutorials/code-flow

Функции:
- music_play: включить трек/плейлист/альбом
- music_pause: поставить на паузу
- music_skip: следующий трек
- music_now: текущий трек
- music_search: поиск треков
- music_volume: установить громкость
"""

from __future__ import annotations

import os
from typing import Any

import aiohttp

from app.core.logging import get_logger
from app.services.tools import tool

logger = get_logger(__name__)

_CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID", "")
_CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET", "")
_REFRESH_TOKEN = os.environ.get("SPOTIFY_REFRESH_TOKEN", "")
_TOKEN_URL = "https://accounts.spotify.com/api/token"
_API_URL = "https://api.spotify.com/v1"

# Cached access token
_access_token: str = ""
_token_expires: float = 0


def _configured() -> bool:
    return bool(_CLIENT_ID and _CLIENT_SECRET and _REFRESH_TOKEN)


async def _get_token() -> str:
    """Получает или обновляет access token через refresh token."""
    global _access_token, _token_expires
    import time

    if _access_token and time.time() < _token_expires:
        return _access_token

    async with aiohttp.ClientSession() as session:
        async with session.post(
            _TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": _REFRESH_TOKEN,
                "client_id": _CLIENT_ID,
                "client_secret": _CLIENT_SECRET,
            },
            timeout=10,
        ) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Spotify token error: {resp.status}")
            data = await resp.json()
            _access_token = data["access_token"]
            _token_expires = time.time() + data.get("expires_in", 3600) - 60
            return _access_token


async def _api(method: str, path: str, json_data: dict | None = None) -> dict | None:
    token = await _get_token()
    headers = {"Authorization": f"Bearer {token}"}
    async with aiohttp.ClientSession() as session:
        async with session.request(
            method, f"{_API_URL}{path}", headers=headers, json=json_data, timeout=10
        ) as resp:
            if resp.status == 204:
                return {}
            if resp.status >= 400:
                body = await resp.text()
                return {"error": f"{resp.status}: {body[:200]}"}
            if resp.content_length == 0:
                return {}
            return await resp.json()


@tool(name="music_now", description="Показать текущий играющий трек в Spotify.")
async def music_now() -> str:
    if not _configured():
        return "Spotify не настроен. Добавь SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, SPOTIFY_REFRESH_TOKEN в .env."
    try:
        data = await _api("GET", "/me/player/currently-playing")
        if not data or "item" not in data:
            return "Сейчас ничего не играет."
        item = data["item"]
        artists = ", ".join(a["name"] for a in item.get("artists", []))
        name = item.get("name", "")
        is_playing = data.get("is_playing", False)
        status = "▶" if is_playing else "⏸"
        return f"{status} {artists} — {name}"
    except Exception as exc:
        return f"Ошибка: {exc}"


@tool(name="music_play", description="Включить музыку в Spotify. Можно указать запрос для поиска.")
async def music_play(query: str = "") -> str:
    """Включить музыку. Если query пуст — продолжить воспроизведение."""
    if not _configured():
        return "Spotify не настроен."
    try:
        if not query:
            result = await _api("PUT", "/me/player/play")
            if result and "error" in result:
                return f"Ошибка: {result['error']}"
            return "▶ Воспроизведение продолжено."

        # Поиск трека
        async with aiohttp.ClientSession() as session:
            token = await _get_token()
            async with session.get(
                f"{_API_URL}/search",
                params={"q": query, "type": "track", "limit": 1},
                headers={"Authorization": f"Bearer {token}"},
                timeout=10,
            ) as resp:
                data = await resp.json()

        tracks = data.get("tracks", {}).get("items", [])
        if not tracks:
            return f"Не нашёл: {query}"

        track = tracks[0]
        uri = track["uri"]
        artists = ", ".join(a["name"] for a in track.get("artists", []))
        name = track["name"]

        result = await _api("PUT", "/me/player/play", {"uris": [uri]})
        if result and "error" in result:
            return f"Ошибка: {result['error']}"
        return f"▶ {artists} — {name}"
    except Exception as exc:
        return f"Ошибка: {exc}"


@tool(name="music_pause", description="Поставить Spotify на паузу.")
async def music_pause() -> str:
    if not _configured():
        return "Spotify не настроен."
    try:
        result = await _api("PUT", "/me/player/pause")
        if result and "error" in result:
            return f"Ошибка: {result['error']}"
        return "⏸ Пауза."
    except Exception as exc:
        return f"Ошибка: {exc}"


@tool(name="music_skip", description="Следующий трек в Spotify.")
async def music_skip() -> str:
    if not _configured():
        return "Spotify не настроен."
    try:
        result = await _api("POST", "/me/player/next")
        if result and "error" in result:
            return f"Ошибка: {result['error']}"
        return "⏭ Следующий трек."
    except Exception as exc:
        return f"Ошибка: {exc}"


@tool(name="music_volume", description="Установить громкость Spotify (0-100).")
async def music_volume(level: int = 50) -> str:
    if not _configured():
        return "Spotify не настроен."
    level = max(0, min(100, level))
    try:
        result = await _api("PUT", f"/me/player/volume?volume_percent={level}")
        if result and "error" in result:
            return f"Ошибка: {result['error']}"
        return f"🔊 Громкость: {level}%"
    except Exception as exc:
        return f"Ошибка: {exc}"


@tool(name="music_search", description="Поиск треков в Spotify.")
async def music_search(query: str, count: int = 5) -> str:
    if not _configured():
        return "Spotify не настроен."
    try:
        token = await _get_token()
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{_API_URL}/search",
                params={"q": query, "type": "track", "limit": min(count, 10)},
                headers={"Authorization": f"Bearer {token}"},
                timeout=10,
            ) as resp:
                data = await resp.json()

        tracks = data.get("tracks", {}).get("items", [])
        if not tracks:
            return f"Ничего не нашёл по запросу «{query}»."

        lines = []
        for i, t in enumerate(tracks, 1):
            artists = ", ".join(a["name"] for a in t.get("artists", []))
            lines.append(f"{i}. {artists} — {t['name']}")
        return "\n".join(lines)
    except Exception as exc:
        return f"Ошибка: {exc}"
