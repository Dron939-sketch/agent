# services/web_search.py
"""
Сервис для поиска в интернете
Поддерживает DuckDuckGo (бесплатно) и Brave Search API
"""

import aiohttp
import asyncio
import re
from typing import List, Dict, Optional
from urllib.parse import quote_plus
import logging

logger = logging.getLogger(__name__)


class WebSearchService:
    """Сервис для поиска в интернете"""
    
    def __init__(self, api_key: str = None, engine: str = "duckduckgo"):
        self.engine = engine
        self.brave_api_key = api_key
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
    
    async def search(self, query: str, num_results: int = 5) -> List[Dict]:
        """Поиск в интернете"""
        if self.engine == "brave" and self.brave_api_key:
            return await self._search_brave(query, num_results)
        else:
            return await self._search_duckduckgo(query, num_results)
    
    async def _search_duckduckgo(self, query: str, num_results: int = 5) -> List[Dict]:
        """Поиск через DuckDuckGo HTML API (бесплатно, без ключа)"""
        results = []
        url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers, timeout=15) as resp:
                    if resp.status != 200:
                        logger.warning(f"DuckDuckGo returned {resp.status}")
                        return results
                    
                    html = await resp.text()
                    
                    # Парсим результаты
                    # Ищем блоки .result
                    result_pattern = r'<a rel="nofollow" class="result__a" href="([^"]+)"[^>]*>([^<]+)</a>'
                    snippet_pattern = r'<a class="result__snippet"[^>]*>([^<]+(?:<[^>]+>[^<]*</[^>]+>[^<]*)*)</a>'
                    
                    links = re.findall(result_pattern, html)
                    snippets = re.findall(snippet_pattern, html)
                    
                    for i, (link, title) in enumerate(links[:num_results]):
                        # Очищаем HTML от тегов
                        clean_title = re.sub(r'<[^>]+>', '', title).strip()
                        clean_snippet = re.sub(r'<[^>]+>', '', snippets[i] if i < len(snippets) else '').strip()
                        
                        results.append({
                            "title": clean_title,
                            "url": link,
                            "snippet": clean_snippet[:300] + "..." if len(clean_snippet) > 300 else clean_snippet,
                            "source": "duckduckgo"
                        })
                    
        except Exception as e:
            logger.error(f"DuckDuckGo search error: {e}")
        
        return results
    
    async def _search_brave(self, query: str, num_results: int = 5) -> List[Dict]:
        """Поиск через Brave Search API (требуется API ключ)"""
        if not self.brave_api_key:
            return await self._search_duckduckgo(query, num_results)
        
        results = []
        url = f"https://api.search.brave.com/res/v1/web/search?q={quote_plus(query)}&count={num_results}"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers={
                        "Accept": "application/json",
                        "X-Subscription-Token": self.brave_api_key
                    },
                    timeout=15
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for web_result in data.get("web", {}).get("results", []):
                            results.append({
                                "title": web_result.get("title", ""),
                                "url": web_result.get("url", ""),
                                "snippet": web_result.get("description", ""),
                                "source": "brave"
                            })
                    else:
                        logger.warning(f"Brave API returned {resp.status}")
                        
        except Exception as e:
            logger.error(f"Brave search error: {e}")
        
        return results
    
    async def fetch_page_content(self, url: str, max_length: int = 5000) -> Optional[str]:
        """Загружает содержимое страницы (для глубокого анализа)"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers, timeout=10) as resp:
                    if resp.status == 200:
                        html = await resp.text()
                        # Извлекаем текстовое содержимое (убираем теги)
                        text = re.sub(r'<[^>]+>', ' ', html)
                        text = re.sub(r'\s+', ' ', text).strip()
                        return text[:max_length]
        except Exception as e:
            logger.error(f"Fetch page error: {e}")
        
        return None


# Глобальный экземпляр
web_search = WebSearchService()
