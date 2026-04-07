# tools/search_tool.py
"""
Инструмент для поиска в интернете
Определяет, когда AI должен использовать поиск
"""

import json
from typing import Dict, Any, List
import logging

logger = logging.getLogger(__name__)

# Описание инструмента для AI (OpenAI/DeepSeek function calling)
SEARCH_TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "search_web",
        "description": "Search the internet for current information, news, facts, or anything that requires up-to-date data. Use this when you don't know something or need recent information.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query to look up on the internet"
                },
                "num_results": {
                    "type": "integer",
                    "description": "Number of results to return (default 3, max 10)",
                    "default": 3
                }
            },
            "required": ["query"]
        }
    }
}


class SearchTool:
    """Инструмент для поиска в интернете"""
    
    def __init__(self, web_search_service):
        self.web_search = web_search_service
        self.search_history: List[Dict] = []
    
    async def execute(self, query: str, num_results: int = 3) -> Dict[str, Any]:
        """Выполняет поиск и возвращает результаты"""
        logger.info(f"🔍 Поиск: {query}")
        
        results = await self.web_search.search(query, num_results)
        
        # Сохраняем в историю
        self.search_history.append({
            "query": query,
            "results": results,
            "timestamp": None  # будет установлено при вызове
        })
        
        if not results:
            return {
                "success": False,
                "error": "Ничего не найдено",
                "results": []
            }
        
        return {
            "success": True,
            "query": query,
            "results": [
                {
                    "title": r["title"],
                    "url": r["url"],
                    "snippet": r["snippet"]
                }
                for r in results
            ]
        }
    
    def format_results_for_ai(self, results: Dict) -> str:
        """Форматирует результаты для вставки в ответ AI"""
        if not results.get("success"):
            return "По вашему запросу ничего не найдено."
        
        formatted = f"🔍 Результаты поиска по запросу «{results['query']}»:\n\n"
        
        for i, r in enumerate(results["results"], 1):
            formatted += f"{i}. **{r['title']}**\n"
            formatted += f"   {r['snippet'][:200]}...\n"
            formatted += f"   🔗 {r['url']}\n\n"
        
        return formatted


# Глобальный экземпляр
from services.web_search import web_search as ws
search_tool = SearchTool(ws)
