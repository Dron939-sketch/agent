# agents/assistants/voice_assistant.py
"""
Голосовой ассистент
Управляет голосовым взаимодействием
"""

import logging
from typing import Dict, Any, Optional
from ..life_router import LifeRouter, UserProfile

logger = logging.getLogger(__name__)


class VoiceAssistant:
    """Управляет голосовым общением"""
    
    def __init__(self, life_router: LifeRouter):
        self.router = life_router
    
    def get_voice_prompt(self, profile: UserProfile) -> str:
        """Возвращает промпт для голосового режима"""
        vector_data = self.router.get_vector_data(profile.dominant, profile.vectors[profile.dominant])
        
        prompts = {
            "СБ": "Говори кратко и чётко. Без долгих вступлений. По делу.",
            "ТФ": "Говори структурированно. Можно с паузами — я всё равно соберу информацию.",
            "УБ": "Говори логично, с аргументами. Я люблю понимать причинно-следственные связи.",
            "ЧВ": "Говори свободно, как с другом. Эмоции приветствуются."
        }
        
        return prompts.get(profile.dominant, "Говори как удобно, я тебя пойму")
    
    def get_tts_voice(self, profile: UserProfile) -> str:
        """Выбирает голос для TTS"""
        voices = {
            "СБ": "alena",      # твёрдый, уверенный
            "ТФ": "filipp",     # спокойный, размеренный
            "УБ": "ermil",      # нейтральный, аналитичный
            "ЧВ": "jane"        # тёплый, эмпатичный
        }
        
        return voices.get(profile.dominant, "jane")
    
    def get_speech_speed(self, profile: UserProfile) -> float:
        """Скорость речи для TTS"""
        speeds = {
            "СБ": 1.1,   # быстрее
            "ТФ": 1.0,   # нормально
            "УБ": 0.9,   # медленнее
            "ЧВ": 1.0    # нормально
        }
        
        return speeds.get(profile.dominant, 1.0)
    
    def process_voice_command(self, profile: UserProfile, text: str) -> Dict[str, Any]:
        """Обрабатывает голосовую команду"""
        text_lower = text.lower()
        
        # Распознаём интенты
        if any(word in text_lower for word in ["цель", "достичь", "стать"]):
            return {"intent": "goal", "assistant": "goal_assistant"}
        elif any(word in text_lower for word in ["почему", "разобраться", "понять"]):
            return {"intent": "analysis", "assistant": "analysis_assistant"}
        elif any(word in text_lower for word in ["план", "расписание", "напомни"]):
            return {"intent": "schedule", "assistant": "schedule_assistant"}
        elif any(word in text_lower for word in ["как дела", "привет", "расскажи"]):
            return {"intent": "chat", "assistant": "main_assistant"}
        else:
            return {"intent": "unknown", "assistant": "main_assistant"}
    
    def format_voice_response(self, text: str, profile: UserProfile) -> str:
        """Форматирует ответ для голосового вывода"""
        # Убираем маркдаун и лишние символы
        clean_text = text.replace('*', '').replace('_', '').replace('`', '')
        
        # Короткие ответы для голоса
        if len(clean_text) > 500:
            # Находим последнюю точку в пределах 500 символов
            cut_point = clean_text[:500].rfind('.')
            if cut_point > 0:
                clean_text = clean_text[:cut_point + 1] + " Хочешь услышать продолжение?"
        
        return clean_text
