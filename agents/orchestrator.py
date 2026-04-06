# agents/orchestrator.py
"""
Оркестратор агентов
Собирает всё вместе и управляет взаимодействием
"""

import logging
from typing import Dict, Any, Optional
from .life_router import LifeRouter, UserProfile
from .assistants import (
    GoalAssistant, AnalysisAssistant, ScheduleAssistant, VoiceAssistant
)

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """
    Оркестратор — главный дирижёр всей агентной системы
    """
    
    def __init__(self, knowledge_base_path: Optional[str] = None):
        self.router = LifeRouter(knowledge_base_path)
        self.goal_assistant = GoalAssistant(self.router)
        self.analysis_assistant = AnalysisAssistant(self.router)
        self.schedule_assistant = ScheduleAssistant(self.router)
        self.voice_assistant = VoiceAssistant(self.router)
        
        logger.info("✅ Agent Orchestrator инициализирован")
    
    def process_request(self, profile_code: str, user_request: str, context: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Главный метод обработки запроса пользователя
        """
        # 1. Загружаем профиль
        profile = self.router.load_profile(profile_code, **(context or {}))
        
        # 2. Проверяем, нужно ли вмешаться
        if self.router.should_intervene(profile, user_request):
            intervention = self.router.get_intervention_message(profile, user_request)
            return {
                "status": "intervention",
                "response": intervention,
                "profile": profile.profile_code,
                "dominant": profile.dominant
            }
        
        # 3. Определяем реальную потребность
        real_need = self.router.get_real_need(profile, user_request)
        
        # 4. Маршрутизируем к нужному ассистенту
        assistant_name = self.router.route_to_assistant(profile, user_request)
        
        # 5. Получаем ответ от ассистента
        response = self._call_assistant(assistant_name, profile, user_request)
        
        # 6. Возвращаем результат
        return {
            "status": "success",
            "response": response,
            "assistant": assistant_name,
            "profile": profile.profile_code,
            "dominant": profile.dominant,
            "real_need": real_need.get("real_need", "")
        }
    
    def _call_assistant(self, assistant_name: str, profile: UserProfile, request: str) -> str:
        """Вызывает соответствующего ассистента"""
        
        if assistant_name == "goal_assistant":
            goals = self.goal_assistant.suggest_goals(profile)
            if goals:
                return f"Исходя из твоего профиля, тебе могут подойти такие цели:\n" + \
                       "\n".join([f"• {g['title']}" for g in goals])
            return "Давай определим, какая цель для тебя сейчас самая важная."
        
        elif assistant_name == "analysis_assistant":
            prompt = self.analysis_assistant.get_analysis_prompt(profile, request)
            # Здесь будет вызов AI с этим промптом
            return f"Анализирую твой вопрос с учётом твоего профиля. " + \
                   f"Твой тип — {profile.dominant}, уровень {profile.dominant_level}. " + \
                   f"Давай разберёмся глубже."
        
        elif assistant_name == "schedule_assistant":
            tips = self.schedule_assistant.get_productivity_tips(profile)
            return "Вот несколько советов по организации времени:\n" + \
                   "\n".join([f"• {tip}" for tip in tips[:3]])
        
        elif assistant_name == "voice_assistant":
            voice_prompt = self.voice_assistant.get_voice_prompt(profile)
            return f"{voice_prompt}\n\nЧем могу помочь?"
        
        else:
            # main_assistant
            comm_strategy = self.router.get_communication_strategy(profile)
            return f"Я Фреди, твой виртуальный помощник. " + \
                   f"Буду говорить {comm_strategy.get('message_format', 'понятно и по делу')}. " + \
                   f"Чем могу быть полезен?"
    
    def get_agent_context(self, profile_code: str) -> Dict[str, Any]:
        """Возвращает полный контекст для агента"""
        profile = self.router.load_profile(profile_code)
        return self.router.create_agent_context(profile)
