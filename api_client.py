# api_client.py
import aiohttp
import asyncio
from typing import Dict, Any, Optional

class APIClient:
    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def get_session(self) -> aiohttp.ClientSession:
        if not self._session or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session
    
    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
    
    async def get(self, url: str, params: Dict = None, headers: Dict = None) -> Dict:
        session = await self.get_session()
        async with session.get(url, params=params, headers=headers) as resp:
            return await resp.json()
    
    async def post(self, url: str, data: Dict = None, json: Dict = None, headers: Dict = None) -> Dict:
        session = await self.get_session()
        async with session.post(url, data=data, json=json, headers=headers) as resp:
            return await resp.json()
