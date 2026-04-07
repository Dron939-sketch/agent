"""OpenWeatherMap-обёртка."""

from __future__ import annotations

from typing import Any

import aiohttp

from app.core.config import Config
from app.core.logging import get_logger

logger = get_logger(__name__)


class WeatherService:
    base = "https://api.openweathermap.org/data/2.5/weather"

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or Config.OPENWEATHER_API_KEY

    async def get(self, city: str) -> dict[str, Any] | None:
        if not self.api_key:
            return None
        params = {"q": city, "appid": self.api_key, "units": "metric", "lang": "ru"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.base, params=params, timeout=10) as resp:
                    if resp.status != 200:
                        logger.error("OpenWeather %s", resp.status)
                        return None
                    data = await resp.json()
                    return {
                        "city": data.get("name"),
                        "temperature": data.get("main", {}).get("temp"),
                        "feels_like": data.get("main", {}).get("feels_like"),
                        "humidity": data.get("main", {}).get("humidity"),
                        "description": (data.get("weather") or [{}])[0].get("description"),
                        "icon": (data.get("weather") or [{}])[0].get("icon"),
                        "wind_speed": data.get("wind", {}).get("speed"),
                    }
        except Exception as exc:  # pragma: no cover
            logger.exception("Weather error: %s", exc)
            return None
