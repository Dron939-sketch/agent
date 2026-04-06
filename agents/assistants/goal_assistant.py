# agents/assistants/goal_assistant.py
"""
Ассистент по целям
Знает, какие цели подходят для каждого профиля
"""

import logging
from typing import Dict, Any, List, Optional
from ..life_router import LifeRouter, UserProfile

logger = logging.getLogger(__name__)


class GoalAssistant:
    """Помогает с постановкой и достижением целей"""
    
    # База целей по мастям и уровням
    GOALS_DB = {
        "СБ": {
            1: ["Научиться говорить «нет»", "Защитить личные границы", "Перестать быть жертвой"],
            2: ["Перестать избегать конфликтов", "Развить уверенность", "Научиться отстаивать своё"],
            3: ["Контролировать агрессию", "Направить силу в спорт", "Развить дисциплину"],
            4: ["Стать защитником для близких", "Развить стратегическое мышление", "Научиться защищать"],
            5: ["Монетизировать силу", "Стать профессионалом", "Найти работу по призванию"],
            6: ["Создать систему безопасности", "Стать лидером", "Воспитывать последователей"]
        },
        "ТФ": {
            1: ["Найти стабильную работу", "Развить базовые навыки", "Научиться планировать день"],
            2: ["Повысить квалификацию", "Научиться планировать бюджет", "Развить профессионализм"],
            3: ["Увеличить доход", "Найти лучшее место", "Развить востребованные навыки"],
            4: ["Работать на себя", "Развить мастерство", "Создать портфолио"],
            5: ["Нанимать людей", "Создать команду", "Делегировать задачи"],
            6: ["Создать бизнес", "Масштабироваться", "Создать пассивный доход"]
        },
        "УБ": {
            1: ["Начать читать книги", "Развить любопытство", "Задавать вопросы"],
            2: ["Учиться проверять факты", "Развить критическое мышление", "Отличать факты от мнений"],
            3: ["Проверять информацию", "Искать причины явлений", "Развивать аналитику"],
            4: ["Проверять авторитетов", "Думать самостоятельно", "Развивать независимость"],
            5: ["Развить системное мышление", "Анализировать сложные системы", "Строить модели"],
            6: ["Создать методологию", "Обучать других", "Писать статьи/книги"]
        },
        "ЧВ": {
            1: ["Научиться просить помощь честно", "Развить самодостаточность", "Перестать манипулировать"],
            2: ["Найти себя", "Перестать копировать других", "Развить аутентичность"],
            3: ["Развить эмпатию", "Учиться честному общению", "Строить искренние отношения"],
            4: ["Помогать вместо манипуляции", "Стать лидером-слугой", "Развить влияние"],
            5: ["Создать личный бренд", "Развить влияние", "Научиться вдохновлять"],
            6: ["Создать сообщество", "Обучать лидеров", "Создать движение"]
        }
    }
    
    def __init__(self, life_router: LifeRouter):
        self.router = life_router
    
    def suggest_goals(self, profile: UserProfile, limit: int = 3) -> List[Dict[str, str]]:
        """Предлагает цели, которые реально нужны пользователю"""
        level = profile.vectors.get(profile.dominant, 3)
        
        # Получаем цели для доминантной масти
        goals = self.GOALS_DB.get(profile.dominant, {}).get(level, [])
        
        # Добавляем цели из БЗ
        vector_data = self.router.get_vector_data(profile.dominant, level)
        real_need = vector_data.get("what_they_need", "")
        if real_need and real_need not in goals:
            goals.insert(0, real_need)
        
        # Форматируем результат
        result = []
        for i, goal in enumerate(goals[:limit]):
            result.append({
                "id": f"{profile.dominant}_{level}_{i}",
                "title": goal,
                "priority": i == 0,
                "vector": profile.dominant,
                "level": level
            })
        
        return result
    
    def check_feasibility(self, goal: str, profile: UserProfile, context: Dict) -> Dict:
        """Проверяет достижимость цели"""
        level = profile.vectors.get(profile.dominant, 3)
        
        # Базовая оценка сложности
        difficulty = "medium"
        if level <= 2:
            difficulty = "hard"  # низкий уровень = сложнее
        elif level >= 5:
            difficulty = "easy"  # высокий уровень = легче
        
        return {
            "goal": goal,
            "feasible": difficulty != "hard",
            "difficulty": difficulty,
            "estimated_time": self._estimate_time(goal, profile),
            "recommendation": self._get_recommendation(goal, profile)
        }
    
    def _estimate_time(self, goal: str, profile: UserProfile) -> str:
        """Оценивает время на достижение цели"""
        level = profile.vectors.get(profile.dominant, 3)
        
        estimates = {
            1: "3-6 месяцев",
            2: "2-4 месяца", 
            3: "1-3 месяца",
            4: "3-6 недель",
            5: "2-4 недели",
            6: "1-2 недели"
        }
        
        return estimates.get(level, "1-3 месяца")
    
    def _get_recommendation(self, goal: str, profile: UserProfile) -> str:
        """Даёт рекомендацию по достижению цели"""
        vector_data = self.router.get_vector_data(profile.dominant, profile.vectors[profile.dominant])
        how_to_lead = vector_data.get("how_to_lead", "")
        
        if how_to_lead:
            return how_to_lead
        
        recommendations = {
            "СБ": "Разбивай цель на маленькие шаги и отмечай каждый успех",
            "ТФ": "Составь чёткий план и следуй ему, фиксируя прогресс",
            "УБ": "Изучи тему, найди закономерности, проверь на практике",
            "ЧВ": "Найди единомышленников, делись прогрессом, получай поддержку"
        }
        
        return recommendations.get(profile.dominant, "Начни с малого и двигайся постепенно")
    
    def break_down_goal(self, goal: str, profile: UserProfile) -> List[str]:
        """Разбивает цель на подшаги"""
        # Базовая разбивка для всех
        steps = [
            f"Шаг 1: Определить, что именно значит «{goal}» лично для тебя",
            "Шаг 2: Оценить текущую ситуацию и ресурсы",
            "Шаг 3: Составить план действий на неделю",
            "Шаг 4: Сделать первый маленький шаг сегодня",
            "Шаг 5: Отслеживать прогресс и корректировать план"
        ]
        
        # Адаптация под масть
        if profile.dominant == "СБ":
            steps[0] = "Шаг 1: Признать, что это действительно важно для тебя"
            steps[3] = "Шаг 4: Сделать первый шаг, несмотря на страх"
        elif profile.dominant == "ТФ":
            steps[2] = "Шаг 3: Составить детальный пошаговый план"
        elif profile.dominant == "УБ":
            steps[1] = "Шаг 2: Проанализировать, что уже известно об этом"
        elif profile.dominant == "ЧВ":
            steps.insert(1, "Шаг 1.5: Рассказать о цели кому-то, кто поддержит")
        
        return steps
