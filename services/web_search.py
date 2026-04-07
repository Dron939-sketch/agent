# services/web_search.py
import aiohttp
import asyncio
from typing import List, Dict, Optional

class WebSearchService:
    """Сервис для поиска в интернете"""
    
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (compatible; FrediBot/1.0)"
        }
    
    async def search(self, query: str, num_results: int = 5) -> List[Dict]:
        """Поиск через DuckDuckGo (бесплатно, без API-ключа)"""
        # Используем HTML API DuckDuckGo
        url = f"https://html.duckduckgo.com/html/?q={query}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=self.headers) as resp:
                html = await resp.text()
                return self._parse_results(html, num_results)
    
    async def fetch_page(self, url: str) -> Optional[str]:
        """Загружает содержимое страницы"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers, timeout=10) as resp:
                    return await resp.text()
        except Exception as e:
            return None
