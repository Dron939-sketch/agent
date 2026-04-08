"""Proactive Trigger Engine — Фреди сам начинает взаимодействие.

Sprint 6: движок триггеров с приоритетами, оценка каждые 30 секунд.
"""

from .engine import TriggerEngine, get_trigger_engine
from .base import Trigger, TriggerResult, Priority

__all__ = [
    "TriggerEngine",
    "get_trigger_engine",
    "Trigger",
    "TriggerResult",
    "Priority",
]
