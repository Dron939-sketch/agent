# agents/life_router.py
"""
Главный агент-маршрутизатор
Принимает решения, а не просто отвечает
"""

import json
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class UserProfile:
    """Нормализованный профиль пользователя"""
    profile_code: str  # "СБ-4_ТФ-5_УБ-3_ЧВ-6"
    vectors: Dict[str, int] = field(default_factory=dict)  # {"СБ": 4, ...}
    varitype_levels: Dict[str, Any] = field(default_factory=dict)
    dominant: str = ""
    dominant_level: str = ""
    perception_type: str = ""
    thinking_level: int = 5
    deep_patterns: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if not self.vectors and self.profile_code:
            self.vectors = self._parse_profile_code(self.profile_code)
    
    def _parse_profile_code(self, code: str) -> Dict[str, int]:
        """Парсит СБ-4_ТФ-5_УБ-3_ЧВ-6 в словарь"""
        result = {}
        parts = code.split('_')
        for part in parts:
            if '-' in part:
                vector, level = part.split('-')
                result[vector] = int(level)
        return result


class LifeRouter:
    """
    Главный агент, который:
    1. Загружает профиль пользователя
    2. Определяет его реальные потребности
    3. Направляет к нужному ассистенту
    4. Принимает решения, а не просто отвечает
    """
    
    # Маппинг уровней теста -> уровни Вариатики
    LEVEL_MAPPING = {
        1: {"varitype": 6, "name": "Шестёрка", "stage": "жертва"},
        2: {"varitype": 7, "name": "Семёрка", "stage": "избегание"},
        3: {"varitype": 8, "name": "Восьмёрка", "stage": "провокация"},
        4: {"varitype": 9, "name": "Девятка", "stage": "защита"},
        5: {"varitype": 10, "name": "Десятка", "stage": "профессионал"},
        6: {"varitype": "11+", "name": "Валет+", "stage": "мастер"}
    }
    
    def __init__(self, knowledge_base_path: Optional[str] = None):
        if knowledge_base_path is None:
            # Ищем файл БЗ в стандартных местах
            paths = [
                Path(__file__).parent.parent / "data" / "varitype-kb.json",
                Path("data/varitype-kb.json"),
                Path("varitype-kb.json")
            ]
            for path in paths:
                if path.exists():
                    knowledge_base_path = str(path)
                    break
        
        if knowledge_base_path and Path(knowledge_base_path).exists():
            with open(knowledge_base_path, 'r', encoding='utf-8') as f:
                self.kb = json.load(f)
            logger.info(f"✅ Загружена БЗ из {knowledge_base_path}")
        else:
            logger.warning("⚠️ БЗ не найдена, используется fallback")
            self.kb = self._get_fallback_kb()
    
    def _get_fallback_kb(self) -> Dict:
        """Fallback БЗ на случай отсутствия файла"""
        return {
            "version": "1.0",
            "vectors": {
                "СБ": {"name": "Силовик", "essence": "Выживает через силу"},
                "ТФ": {"name": "Трудяга", "essence": "Выживает через труд"},
                "УБ": {"name": "Умный", "essence": "Выживает через знание"},
                "ЧВ": {"name": "Влиятель", "essence": "Выживает через связи"}
            }
        }
    
    def _parse_profile_code(self, code: str) -> Dict[str, int]:
        """Парсит СБ-4_ТФ-5_УБ-3_ЧВ-6 в словарь"""
        result = {}
        parts = code.split('_')
        for part in parts:
            if '-' in part:
                vector, level = part.split('-')
                result[vector] = int(level)
        return result
    
    def _normalize_level(self, test_level: int) -> Dict:
        """Нормализует уровень теста в уровень Вариатики"""
        return self.LEVEL_MAPPING.get(test_level, self.LEVEL_MAPPING[3])
    
    def _get_dominant(self, vectors: Dict[str, int]) -> str:
        """Определяет доминантную масть"""
        if not vectors:
            return "ЧВ"
        return max(vectors.items(), key=lambda x: x[1])[0]
    
    def load_profile(self, profile_code: str, **kwargs) -> UserProfile:
        """Загружает и нормализует профиль пользователя"""
        vectors = self._parse_profile_code(profile_code)
        dominant = self._get_dominant(vectors)
        
        # Нормализуем уровни
        varitype_levels = {}
        for vector, level in vectors.items():
            varitype_levels[vector] = self._normalize_level(level)
        
        return UserProfile(
            profile_code=profile_code,
            vectors=vectors,
            varitype_levels=varitype_levels,
            dominant=dominant,
            dominant_level=varitype_levels[dominant]["name"],
            perception_type=kwargs.get("perception_type", ""),
            thinking_level=kwargs.get("thinking_level", 5),
            deep_patterns=kwargs.get("deep_patterns", {})
        )
    
    def get_vector_data(self, vector: str, test_level: int) -> Dict:
        """Возвращает данные по вектору из БЗ"""
        if vector not in self.kb.get("vectors", {}):
            return {}
        
        vector_data = self.kb["vectors"][vector]
        level_data = vector_data.get("levels", {}).get(str(test_level), {})
        
        return {
            "name": vector_data.get("name", vector),
            "essence": vector_data.get("essence", ""),
            "level_name": level_data.get("level_name", ""),
            "behavior": level_data.get("behavior", {}),
            "communication": level_data.get("communication", {}),
            "what_they_need": level_data.get("what_they_need", ""),
            "how_to_lead": level_data.get("how_to_lead", "")
        }
    
    def get_real_need(self, profile: UserProfile, user_request: str) -> Dict[str, Any]:
        """
        Определяет, что пользователю на самом деле нужно
        """
        vector_data = self.get_vector_data(profile.dominant, profile.vectors[profile.dominant])
        
        return {
            "user_says": user_request,
            "dominant_vector": profile.dominant,
            "dominant_level": profile.dominant_level,
            "real_need": vector_data.get("what_they_need", "Понять свои истинные желания"),
            "how_to_lead": vector_data.get("how_to_lead", "Слушать и задавать вопросы"),
            "typical_misrequest": self._detect_misrequest(user_request, profile.dominant)
        }
    
    def _detect_misrequest(self, request: str, vector: str) -> Optional[str]:
        """Определяет, просит ли пользователь не то, что нужно"""
        request_lower = request.lower()
        
        misrequests = {
            "СБ": ["научите драться", "как победить", "уничтожь"],
            "ТФ": ["дайте денег", "как быстро разбогатеть", "лёгких денег"],
            "УБ": ["докажите заговор", "все врут", "скрывают правду"],
            "ЧВ": ["как заставить", "как манипулировать", "как влюбить"]
        }
        
        for word in misrequests.get(vector, []):
            if word in request_lower:
                return word
        
        return None
    
    def get_communication_strategy(self, profile: UserProfile) -> Dict[str, Any]:
        """Возвращает, как ИИ должен общаться с пользователем"""
        vector_data = self.get_vector_data(profile.dominant, profile.vectors[profile.dominant])
        
        default_strategy = {
            "preference": "Адаптивный",
            "message_format": "Чётко и понятно",
            "what_to_avoid": "Долгих объяснений",
            "trust_triggers": "Честность и компетентность"
        }
        
        comm = vector_data.get("communication", {})
        return {**default_strategy, **comm}
    
    def route_to_assistant(self, profile: UserProfile, user_request: str) -> str:
        """Определяет, какому ассистенту передать запрос"""
        request_lower = user_request.lower()
        
        # Маршрутизация по ключевым словам
        routes = [
            (["цель", "достичь", "стать", "научиться", "хочу", "мечтаю"], "goal_assistant"),
            (["почему", "что со мной", "глубинный", "разобраться", "понять себя"], "analysis_assistant"),
            (["план", "расписание", "когда", "напомни", "запланируй"], "schedule_assistant"),
            (["голос", "скажи", "расскажи", "объясни"], "voice_assistant")
        ]
        
        for keywords, assistant in routes:
            if any(kw in request_lower for kw in keywords):
                return assistant
        
        return "main_assistant"
    
    def should_intervene(self, profile: UserProfile, user_request: str) -> bool:
        """Определяет, нужно ли вмешаться"""
        misrequest = self._detect_misrequest(user_request, profile.dominant)
        return misrequest is not None
    
    def get_intervention_message(self, profile: UserProfile, user_request: str) -> str:
        """Возвращает сообщение-интервенцию"""
        vector_data = self.get_vector_data(profile.dominant, profile.vectors[profile.dominant])
        real_need = vector_data.get("what_they_need", "")
        
        messages = {
            "СБ": f"Я вижу, ты просишь о силе. Но давай разберёмся, что тебе действительно нужно: {real_need}",
            "ТФ": f"Понимаю желание быстрых денег. Но давай посмотрим на ситуацию глубже: {real_need}",
            "УБ": f"Ты ищешь правду. Давай вместе проверим факты и найдём настоящее объяснение.",
            "ЧВ": f"Вместо манипуляций, давай научимся влиять честно и создавать настоящие связи."
        }
        
        return messages.get(profile.dominant, "Давай разберёмся, что тебе действительно нужно.")
    
    def create_agent_context(self, profile: UserProfile) -> Dict:
        """Создаёт полный контекст для агента"""
        return {
            "profile": {
                "code": profile.profile_code,
                "vectors": profile.vectors,
                "dominant": profile.dominant,
                "dominant_level": profile.dominant_level,
                "perception_type": profile.perception_type,
                "thinking_level": profile.thinking_level
            },
            "varitype_levels": profile.varitype_levels,
            "communication_strategy": self.get_communication_strategy(profile),
            "vector_data": {
                v: self.get_vector_data(v, level) 
                for v, level in profile.vectors.items()
            }
        }
