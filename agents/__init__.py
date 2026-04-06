# agents/__init__.py
"""
Агентная система Фреди
"""

from .life_router import LifeRouter, UserProfile
from .assistants.goal_assistant import GoalAssistant
from .assistants.analysis_assistant import AnalysisAssistant
from .assistants.schedule_assistant import ScheduleAssistant
from .assistants.voice_assistant import VoiceAssistant

__all__ = [
    'LifeRouter',
    'UserProfile', 
    'GoalAssistant',
    'AnalysisAssistant',
    'ScheduleAssistant',
    'VoiceAssistant'
]
