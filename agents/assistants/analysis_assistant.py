# agents/assistants/analysis_assistant.py
"""
Ассистент по глубинному анализу
Помогает разобраться в себе
"""

import logging
from typing import Dict, Any, List, Optional
from ..life_router import LifeRouter, UserProfile

logger = logging.getLogger(__name__)


class AnalysisAssistant:
    """Помогает с глубинным самоанализом"""
    
    def __init__(self, life_router: LifeRouter):
        self.router = life_router
    
    def get_analysis_prompt(self, profile: UserProfile, question: str) -> str:
        """Создаёт промпт для глубокого анализа"""
        vector_data = self.router.get_vector_data(profile.dominant, profile.vectors[profile.dominant])
        
        prompt = f"""
Ты психолог Фреди. Проведи анализ вопроса пользователя с учётом его профиля.

ПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ:
- Доминантная масть: {profile.dominant} ({vector_data.get('name', '')})
- Уровень: {profile.dominant_level}
- Тип восприятия: {profile.perception_type}
- Уровень мышления: {profile.thinking_level}/9
- Глубинный паттерн: {profile.deep_patterns.get('attachment', 'не определён')}

ОСОБЕННОСТИ ЭТОГО ТИПА:
- Суть: {vector_data.get('essence', '')}
- Что на самом деле нужно: {vector_data.get('what_they_need', '')}
- Слепая зона: {vector_data.get('behavior', {}).get('blind_spot', '')}

ВОПРОС ПОЛЬЗОВАТЕЛЯ: {question}

Проведи анализ, учитывая:
1. Глубинные причины его вопроса
2. Что он на самом деле хочет понять
3. Как его тип восприятия влияет на видение проблемы
4. Конкретные шаги для проработки

Ответь на русском, обращайся на «ты», используй простой язык.
"""
        return prompt
    
    def get_reflection_questions(self, profile: UserProfile, topic: str) -> List[str]:
        """Генерирует вопросы для рефлексии"""
        questions = [
            f"Что для тебя значит «{topic}»?",
            "Как это проявляется в твоей жизни?",
            "Когда ты впервые это заметил?",
            "Что было до этого?",
            "Что ты чувствуешь, когда думаешь об этом?"
        ]
        
        # Адаптация под масть
        if profile.dominant == "СБ":
            questions.append("Как это влияет на твоё чувство безопасности?")
            questions.append("Что бы ты хотел изменить в этой ситуации?")
        elif profile.dominant == "ТФ":
            questions.append("Как это влияет на твою работу/доход?")
            questions.append("Что конкретно можно сделать, чтобы это изменить?")
        elif profile.dominant == "УБ":
            questions.append("Какие закономерности ты замечаешь?")
            questions.append("Как это объясняется с точки зрения логики?")
        elif profile.dominant == "ЧВ":
            questions.append("Как это влияет на твои отношения с людьми?")
            questions.append("Что бы сказали о тебе близкие в этой ситуации?")
        
        return questions
    
    def get_insight(self, profile: UserProfile, pattern: str) -> str:
        """Даёт инсайт на основе выявленного паттерна"""
        insights = {
            "СБ": "Твоя реакция на угрозу — это древний механизм выживания. Но сейчас ты не в джунглях. Можно научиться реагировать иначе.",
            "ТФ": "Ты привык полагаться только на себя. Но делегирование — это не слабость, а рост.",
            "УБ": "Поиск истины — это важно. Но иногда знание без действия — это просто знание.",
            "ЧВ": "Ты чувствуешь других лучше, чем себя. Попробуй направить эту эмпатию внутрь."
        }
        
        return insights.get(profile.dominant, "У каждого паттерна есть своя история. Давай исследуем твою.")
    
    def identify_block(self, profile: UserProfile, issue: str) -> Dict[str, Any]:
        """Определяет возможный блок/ограничение"""
        block_map = {
            "СБ": {
                "keywords": ["страх", "агрессия", "защита", "конфликт"],
                "block": "Страх проявления слабости",
                "workaround": "Начни с малого: скажи «нет» в безопасной ситуации"
            },
            "ТФ": {
                "keywords": ["лень", "устал", "нет времени", "сложно"],
                "block": "Страх не справиться или перфекционизм",
                "workaround": "Разбей задачу на микрошаги. Сделай только первый."
            },
            "УБ": {
                "keywords": ["не понимаю", "запутался", "противоречиво", "нелогично"],
                "block": "Паралич анализом — нужно слишком много понять перед действием",
                "workaround": "Прими временную гипотезу и проверь её на практике"
            },
            "ЧВ": {
                "keywords": ["один", "не поймут", "осудят", "отвергнут"],
                "block": "Страх отвержения и зависимости от чужого мнения",
                "workaround": "Сделай что-то для себя, не спрашивая разрешения"
            }
        }
        
        issue_lower = issue.lower()
        
        for vector, data in block_map.items():
            for keyword in data["keywords"]:
                if keyword in issue_lower:
                    return {
                        "vector": vector,
                        "block": data["block"],
                        "workaround": data["workaround"],
                        "matches_profile": vector == profile.dominant
                    }
        
        return {
            "vector": profile.dominant,
            "block": "Неопределённое ограничение",
            "workaround": "Начни с малого и наблюдай за реакцией",
            "matches_profile": True
        }
