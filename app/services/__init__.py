"""External integrations: LLM, voice, weather, backups, scheduler.

GitHub/CityInfo сервисы перенесём в следующем PR — они крупные.
"""

from .backup import BackupService
from .llm import DeepSeekClient, LLMClient, default_llm
from .scheduler import TaskScheduler
from .voice import VoiceService
from .weather import WeatherService

__all__ = [
    "LLMClient",
    "DeepSeekClient",
    "default_llm",
    "VoiceService",
    "WeatherService",
    "BackupService",
    "TaskScheduler",
]
