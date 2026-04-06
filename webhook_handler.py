# webhook_handler.py
import json
import logging
from typing import Dict, Any, Callable
from fastapi import Request, HTTPException

logger = logging.getLogger(__name__)

class WebhookManager:
    def __init__(self):
        self._handlers: Dict[str, Callable] = {}
    
    def register(self, path: str, handler: Callable):
        """Регистрирует обработчик вебхука"""
        self._handlers[path] = handler
    
    async def handle(self, path: str, request: Request) -> Dict[str, Any]:
        """Обрабатывает входящий вебхук"""
        handler = self._handlers.get(path)
        if not handler:
            raise HTTPException(status_code=404, detail=f"No handler for {path}")
        
        try:
            data = await request.json()
            return await handler(data)
        except Exception as e:
            logger.error(f"Webhook error: {e}")
            raise HTTPException(status_code=500, detail=str(e))
