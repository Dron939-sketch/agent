"""Home Assistant интеграция — управление умным домом.

Настройка в .env:
  HASS_URL=http://homeassistant.local:8123
  HASS_TOKEN=long-lived-access-token

Функции:
- hass_state: состояние устройства (свет, температура, etc.)
- hass_turn_on: включить устройство
- hass_turn_off: выключить устройство
- hass_set_temp: установить температуру
- hass_scene: активировать сцену
"""

from __future__ import annotations

import os

import aiohttp

from app.core.logging import get_logger
from app.services.tools import tool

logger = get_logger(__name__)

_HASS_URL = os.environ.get("HASS_URL", "").rstrip("/")
_HASS_TOKEN = os.environ.get("HASS_TOKEN", "")


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_HASS_TOKEN}",
        "Content-Type": "application/json",
    }


def _configured() -> bool:
    return bool(_HASS_URL and _HASS_TOKEN)


@tool(name="hass_state", description="Получить состояние устройства в Home Assistant.")
async def hass_state(entity_id: str) -> str:
    """Возвращает состояние устройства. Пример: light.living_room, sensor.temperature."""
    if not _configured():
        return "Home Assistant не настроен. Добавь HASS_URL и HASS_TOKEN в .env."

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{_HASS_URL}/api/states/{entity_id}",
                headers=_headers(),
                timeout=5,
            ) as resp:
                if resp.status == 404:
                    return f"Устройство {entity_id} не найдено."
                if resp.status != 200:
                    return f"Ошибка: {resp.status}"
                data = await resp.json()
                state = data.get("state", "unknown")
                friendly_name = data.get("attributes", {}).get("friendly_name", entity_id)
                unit = data.get("attributes", {}).get("unit_of_measurement", "")
                return f"{friendly_name}: {state}{' ' + unit if unit else ''}"
    except Exception as exc:
        return f"Ошибка: {exc}"


@tool(name="hass_turn_on", description="Включить устройство через Home Assistant.")
async def hass_turn_on(entity_id: str) -> str:
    """Включает устройство (свет, розетка, и т.д.)."""
    return await _call_service(entity_id, "turn_on")


@tool(name="hass_turn_off", description="Выключить устройство через Home Assistant.")
async def hass_turn_off(entity_id: str) -> str:
    """Выключает устройство."""
    return await _call_service(entity_id, "turn_off")


@tool(name="hass_scene", description="Активировать сцену в Home Assistant.")
async def hass_scene(scene_name: str) -> str:
    """Активирует сцену. Пример: scene.movie_time, scene.good_night."""
    if not _configured():
        return "Home Assistant не настроен."

    entity_id = scene_name if scene_name.startswith("scene.") else f"scene.{scene_name}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{_HASS_URL}/api/services/scene/turn_on",
                headers=_headers(),
                json={"entity_id": entity_id},
                timeout=5,
            ) as resp:
                if resp.status == 200:
                    return f"Сцена {scene_name} активирована."
                return f"Ошибка: {resp.status}"
    except Exception as exc:
        return f"Ошибка: {exc}"


@tool(name="hass_set_temp", description="Установить температуру на термостате.")
async def hass_set_temp(entity_id: str, temperature: float) -> str:
    """Устанавливает целевую температуру. entity_id: climate.living_room."""
    if not _configured():
        return "Home Assistant не настроен."

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{_HASS_URL}/api/services/climate/set_temperature",
                headers=_headers(),
                json={"entity_id": entity_id, "temperature": temperature},
                timeout=5,
            ) as resp:
                if resp.status == 200:
                    return f"Температура установлена: {temperature}°C"
                return f"Ошибка: {resp.status}"
    except Exception as exc:
        return f"Ошибка: {exc}"


async def _call_service(entity_id: str, action: str) -> str:
    if not _configured():
        return "Home Assistant не настроен."

    domain = entity_id.split(".")[0] if "." in entity_id else "homeassistant"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{_HASS_URL}/api/services/{domain}/{action}",
                headers=_headers(),
                json={"entity_id": entity_id},
                timeout=5,
            ) as resp:
                if resp.status == 200:
                    return f"{entity_id} — {action} выполнено."
                return f"Ошибка: {resp.status}"
    except Exception as exc:
        return f"Ошибка: {exc}"
