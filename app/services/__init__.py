"""External integrations: LLM, voice, weather, backups, scheduler.

GitHub/CityInfo сервисы перенесём в следующем PR — они крупные.
"""

from .backup import BackupService
from .llm import (
    AnthropicClient,
    ChatMessage,
    ChatResponse,
    DeepSeekClient,
    LLMClient,
    LLMError,
    LLMRouter,
    OllamaClient,
    OpenAIClient,
    default_llm,
    default_router,
)
from .scheduler import TaskScheduler
from .voice import VoiceService
from .weather import WeatherService

__all__ = [
    "LLMClient",
    "LLMError",
    "LLMRouter",
    "ChatMessage",
    "ChatResponse",
    "AnthropicClient",
    "DeepSeekClient",
    "OpenAIClient",
    "OllamaClient",
    "default_llm",
    "default_router",
    "VoiceService",
    "WeatherService",
    "BackupService",
    "TaskScheduler",
]
