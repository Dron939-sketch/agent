# scheduler.py
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, Callable, Optional
from database import Database

logger = logging.getLogger(__name__)

class TaskScheduler:
    def __init__(self, db: Database):
        self.db = db
        self.running = False
        self._handlers: Dict[str, Callable] = {}
    
    def register_handler(self, task_type: str, handler: Callable):
        """Регистрирует обработчик для типа задачи"""
        self._handlers[task_type] = handler
    
    async def start(self):
        """Запускает планировщик"""
        self.running = True
        asyncio.create_task(self._run())
        logger.info("✅ Планировщик задач запущен")
    
    async def _run(self):
        while self.running:
            try:
                tasks = self.db.get_pending_tasks()
                for task in tasks:
                    handler = self._handlers.get(task["task_type"])
                    if handler:
                        try:
                            result = await handler(task["user_id"], task["data"])
                            self.db.update_task_status(task["id"], "completed", result)
                        except Exception as e:
                            logger.error(f"Task {task['id']} failed: {e}")
                            self.db.update_task_status(task["id"], "failed", {"error": str(e)})
                    else:
                        logger.warning(f"No handler for task type: {task['task_type']}")
                        self.db.update_task_status(task["id"], "no_handler")
                
                await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"Scheduler error: {e}")
                await asyncio.sleep(10)
    
    async def schedule_reminder(self, user_id: str, message: str, remind_at: datetime):
        """Планирует напоминание"""
        self.db.add_task(user_id, "reminder", {"message": message}, remind_at)
    
    async def schedule_backup(self, interval_hours: int = 24):
        """Планирует резервное копирование"""
        self.db.add_task("system", "backup", {"interval_hours": interval_hours})
    
    async def schedule_daily_summary(self, user_id: str, time: str = "20:00"):
        """Планирует ежедневную сводку"""
        self.db.add_task(user_id, "daily_summary", {}, datetime.now())
