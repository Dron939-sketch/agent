# tools/reminder_tool.py
"""
Инструмент для создания напоминаний
"""

import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

REMINDER_TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "create_reminder",
        "description": "Create a reminder for the user. Use this when the user asks to be reminded about something at a specific time.",
        "parameters": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "The message to remind the user"
                },
                "remind_at": {
                    "type": "string",
                    "description": "When to remind (ISO format: YYYY-MM-DD HH:MM or relative like 'in 1 hour', 'tomorrow at 10am')"
                }
            },
            "required": ["message", "remind_at"]
        }
    }
}


class ReminderTool:
    """Инструмент для создания напоминаний"""
    
    def __init__(self, db):
        self.db = db
    
    def parse_time(self, time_str: str) -> Optional[datetime]:
        """Парсит время из текста"""
        time_str = time_str.lower().strip()
        now = datetime.now()
        
        # Относительные выражения
        if "in" in time_str:
            import re
            numbers = re.findall(r'\d+', time_str)
            if numbers:
                num = int(numbers[0])
                if "minute" in time_str:
                    return now + timedelta(minutes=num)
                elif "hour" in time_str:
                    return now + timedelta(hours=num)
                elif "day" in time_str:
                    return now + timedelta(days=num)
                elif "week" in time_str:
                    return now + timedelta(weeks=num)
        
        # tomorrow at X
        if "tomorrow" in time_str:
            # Извлекаем время
            import re
            time_match = re.search(r'(\d{1,2})[:.]?(\d{2})?', time_str)
            if time_match:
                hour = int(time_match.group(1))
                minute = int(time_match.group(2)) if time_match.group(2) else 0
                result = now.replace(hour=hour, minute=minute, second=0, microsecond=0) + timedelta(days=1)
                if result < now:
                    result += timedelta(days=1)
                return result
        
        # today at X
        if "today" in time_str:
            import re
            time_match = re.search(r'(\d{1,2})[:.]?(\d{2})?', time_str)
            if time_match:
                hour = int(time_match.group(1))
                minute = int(time_match.group(2)) if time_match.group(2) else 0
                result = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                if result < now:
                    result += timedelta(days=1)
                return result
        
        # ISO формат
        try:
            return datetime.fromisoformat(time_str)
        except:
            pass
        
        return None
    
    async def execute(self, user_id: str, message: str, remind_at: str) -> Dict[str, Any]:
        """Создаёт напоминание"""
        remind_time = self.parse_time(remind_at)
        
        if not remind_time:
            return {
                "success": False,
                "error": f"Не удалось распознать время: {remind_at}. Используйте форматы: 'завтра в 10:00', 'через 1 час', '2024-12-31 23:59'"
            }
        
        # Сохраняем в БД
        self.db.add_task(user_id, "reminder", {
            "message": message,
            "scheduled_at": remind_time.isoformat()
        }, remind_time)
        
        return {
            "success": True,
            "message": f"✅ Напоминание создано на {remind_time.strftime('%d.%m.%Y %H:%M')}: {message}",
            "remind_at": remind_time.isoformat()
        }


# Глобальный экземпляр (будет инициализирован в main)
reminder_tool = None
