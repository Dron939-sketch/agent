# agents/assistants/__init__.py
"""
Под-ассистенты Фреди
"""

from .goal_assistant import GoalAssistant
from .analysis_assistant import AnalysisAssistant
from .schedule_assistant import ScheduleAssistant
from .voice_assistant import VoiceAssistant

__all__ = [
    'GoalAssistant',
    'AnalysisAssistant', 
    'ScheduleAssistant',
    'VoiceAssistant'
]
