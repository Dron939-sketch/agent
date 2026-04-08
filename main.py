#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Фреди - Автономный AI-помощник
Версия 5.0 - Полностью автономный ассистент
С функциями: голосовой ввод, создание приложений, сбор данных о городе,
планировщик задач, аутентификация, резервное копирование, вебхуки
"""

import os
import sys
import asyncio
import logging
import json
import base64
import re
import sqlite3
import hashlib
import secrets
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Optional, Dict, Any, List, Callable
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from fastapi import FastAPI, Request, HTTPException, WebSocket, WebSocketDisconnect, UploadFile, File, Form, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn
import aiohttp
import aiofiles

# ============================================
# КОНФИГУРАЦИЯ
# ============================================

class Config:
    # API ключи
    DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
    YANDEX_API_KEY = os.environ.get("YANDEX_API_KEY", "")
    OPENWEATHER_API_KEY = os.environ.get("OPENWEATHER_API_KEY", "")
    GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
    GITHUB_REPO = os.environ.get("GITHUB_REPO", "")
    
    # Настройки приложения
    APP_NAME = "Фреди AI Помощник"
    APP_VERSION = "5.0.0"
    SECRET_KEY = os.environ.get("SECRET_KEY", secrets.token_hex(32))
    PORT = int(os.environ.get("PORT", 8000))
    
    # Пути
    BASE_DIR = Path(__file__).parent
    DATA_DIR = BASE_DIR / "data"
    BACKUP_DIR = BASE_DIR / "backups"
    LOGS_DIR = BASE_DIR / "logs"
    STATIC_DIR = BASE_DIR / "static"
    
    # Создаём директории
    DATA_DIR.mkdir(exist_ok=True)
    BACKUP_DIR.mkdir(exist_ok=True)
    LOGS_DIR.mkdir(exist_ok=True)
    STATIC_DIR.mkdir(exist_ok=True)
    
    # База данных
    DATABASE_PATH = DATA_DIR / "assistant.db"


# ============================================
# НАСТРОЙКА ЛОГИРОВАНИЯ
# ============================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(Config.LOGS_DIR / "assistant.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# ============================================
# БАЗА ДАННЫХ
# ============================================

class Database:
    """Постоянное хранилище данных"""
    
    def __init__(self, db_path: Path = Config.DATABASE_PATH):
        self.db_path = db_path
        self._init_tables()
        logger.info(f"✅ База данных инициализирована: {db_path}")
    
    def _init_tables(self):
        with sqlite3.connect(self.db_path) as conn:
            # Пользователи
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    username TEXT UNIQUE,
                    email TEXT UNIQUE,
                    password_hash TEXT,
                    profile TEXT,
                    context TEXT,
                    settings TEXT,
                    is_active INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Сессии
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY,
                    user_id TEXT,
                    expires_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)
            
            # Сообщения
            conn.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT,
                    role TEXT,
                    content TEXT,
                    metadata TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)
            
            # Задачи
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT,
                    task_type TEXT,
                    status TEXT DEFAULT 'pending',
                    data TEXT,
                    scheduled_at TIMESTAMP,
                    executed_at TIMESTAMP,
                    result TEXT,
                    error TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Логи
            conn.execute("""
                CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    level TEXT,
                    message TEXT,
                    metadata TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Бэкапы
            conn.execute("""
                CREATE TABLE IF NOT EXISTS backups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    backup_path TEXT,
                    size INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # GitHub репозитории
            conn.execute("""
                CREATE TABLE IF NOT EXISTS repositories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT,
                    repo_name TEXT,
                    repo_url TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Индексы
            conn.execute("CREATE INDEX IF NOT EXISTS idx_conversations_user_id ON conversations(user_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_conversations_created_at ON conversations(created_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_user_id ON tasks(user_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_scheduled_at ON tasks(scheduled_at)")
    
    # ========== User methods ==========
    def create_user(self, user_id: str, username: str, email: str, password_hash: str) -> bool:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT INTO users (user_id, username, email, password_hash) VALUES (?, ?, ?, ?)",
                    (user_id, username, email, password_hash)
                )
            return True
        except sqlite3.IntegrityError:
            return False
    
    def get_user(self, user_id: str) -> Optional[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            row = cur.fetchone()
            if row:
                return dict(row)
        return None
    
    def get_user_by_username(self, username: str) -> Optional[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute("SELECT * FROM users WHERE username = ?", (username,))
            row = cur.fetchone()
            if row:
                return dict(row)
        return None
    
    def update_user_profile(self, user_id: str, profile: Dict):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE users SET profile = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?",
                (json.dumps(profile), user_id)
            )
    
    def update_user_context(self, user_id: str, context: Dict):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE users SET context = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?",
                (json.dumps(context), user_id)
            )
    
    def update_user_settings(self, user_id: str, settings: Dict):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE users SET settings = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?",
                (json.dumps(settings), user_id)
            )
    
    # ========== Session methods ==========
    def create_session(self, user_id: str, expires_days: int = 7) -> str:
        token = secrets.token_hex(32)
        expires_at = datetime.now() + timedelta(days=expires_days)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
                (token, user_id, expires_at)
            )
        return token
    
    def get_session(self, token: str) -> Optional[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute("SELECT * FROM sessions WHERE token = ? AND expires_at > CURRENT_TIMESTAMP", (token,))
            row = cur.fetchone()
            if row:
                return dict(row)
        return None
    
    def delete_session(self, token: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
    
    # ========== Conversation methods ==========
    def add_message(self, user_id: str, role: str, content: str, metadata: Dict = None):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO conversations (user_id, role, content, metadata) VALUES (?, ?, ?, ?)",
                (user_id, role, content, json.dumps(metadata or {}))
            )
    
    def get_history(self, user_id: str, limit: int = 50) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                "SELECT role, content, created_at FROM conversations WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
                (user_id, limit)
            )
            rows = cur.fetchall()
            return [{"role": row["role"], "content": row["content"], "timestamp": row["created_at"]} for row in rows][::-1]
    
    def clear_history(self, user_id: str, days: int = 30):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "DELETE FROM conversations WHERE user_id = ? AND created_at < datetime('now', ?)",
                (user_id, f'-{days} days')
            )
    
    # ========== Task methods ==========
    def add_task(self, user_id: str, task_type: str, data: Dict, scheduled_at: datetime = None):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO tasks (user_id, task_type, data, scheduled_at) VALUES (?, ?, ?, ?)",
                (user_id, task_type, json.dumps(data), scheduled_at)
            )
    
    def get_pending_tasks(self) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                "SELECT id, user_id, task_type, data, scheduled_at FROM tasks WHERE status = 'pending' AND (scheduled_at IS NULL OR scheduled_at <= CURRENT_TIMESTAMP)"
            )
            rows = cur.fetchall()
            return [{"id": row["id"], "user_id": row["user_id"], "task_type": row["task_type"], 
                     "data": json.loads(row["data"]), "scheduled_at": row["scheduled_at"]} for row in rows]
    
    def update_task_status(self, task_id: int, status: str, result: Dict = None, error: str = None):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE tasks SET status = ?, executed_at = CURRENT_TIMESTAMP, result = ?, error = ? WHERE id = ?",
                (status, json.dumps(result or {}), error, task_id)
            )
    
    # ========== Log methods ==========
    def add_log(self, level: str, message: str, metadata: Dict = None):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO logs (level, message, metadata) VALUES (?, ?, ?)",
                (level, message, json.dumps(metadata or {}))
            )
    
    # ========== Backup methods ==========
    def create_backup(self) -> str:
        backup_path = Config.BACKUP_DIR / f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        shutil.copy2(self.db_path, backup_path)
        size = backup_path.stat().st_size
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("INSERT INTO backups (backup_path, size) VALUES (?, ?)", (str(backup_path), size))
        return str(backup_path)
    
    def get_backups(self) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute("SELECT id, backup_path, size, created_at FROM backups ORDER BY created_at DESC")
            return [dict(row) for row in cur.fetchall()]
    
    # ========== Repository methods ==========
    def add_repository(self, user_id: str, repo_name: str, repo_url: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO repositories (user_id, repo_name, repo_url) VALUES (?, ?, ?)",
                (user_id, repo_name, repo_url)
            )
    
    def get_repositories(self, user_id: str) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute("SELECT repo_name, repo_url, created_at FROM repositories WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
            return [dict(row) for row in cur.fetchall()]


# ============================================
# АУТЕНТИФИКАЦИЯ
# ============================================

class AuthManager:
    """Управление аутентификацией"""
    
    def __init__(self, db: Database):
        self.db = db
    
    def hash_password(self, password: str) -> str:
        """Хеширует пароль"""
        salt = secrets.token_hex(16)
        return f"{salt}:{hashlib.sha256((salt + password).encode()).hexdigest()}"
    
    def verify_password(self, password: str, hashed: str) -> bool:
        """Проверяет пароль"""
        salt, hash_val = hashed.split(":")
        return hash_val == hashlib.sha256((salt + password).encode()).hexdigest()
    
    def register(self, username: str, email: str, password: str) -> Optional[Dict]:
        """Регистрирует нового пользователя"""
        user_id = f"user_{secrets.token_hex(8)}"
        password_hash = self.hash_password(password)
        
        if self.db.create_user(user_id, username, email, password_hash):
            return {"user_id": user_id, "username": username, "email": email}
        return None
    
    def login(self, username: str, password: str) -> Optional[str]:
        """Авторизует пользователя"""
        user = self.db.get_user_by_username(username)
        if user and self.verify_password(password, user["password_hash"]):
            return self.db.create_session(user["user_id"])
        return None
    
    def verify_token(self, token: str) -> Optional[str]:
        """Проверяет токен сессии"""
        session = self.db.get_session(token)
        if session:
            return session["user_id"]
        return None
    
    def logout(self, token: str):
        self.db.delete_session(token)


# ============================================
# ПЛАНИРОВЩИК ЗАДАЧ
# ============================================

class TaskScheduler:
    """Планировщик фоновых задач"""
    
    def __init__(self, db: Database):
        self.db = db
        self.running = False
        self._handlers: Dict[str, Callable] = {}
        self._task = None
    
    def register_handler(self, task_type: str, handler: Callable):
        self._handlers[task_type] = handler
    
    async def start(self):
        self.running = True
        self._task = asyncio.create_task(self._run())
        logger.info("✅ Планировщик задач запущен")
    
    async def stop(self):
        self.running = False
        if self._task:
            self._task.cancel()
        logger.info("🛑 Планировщик задач остановлен")
    
    async def _run(self):
        while self.running:
            try:
                tasks = self.db.get_pending_tasks()
                for task in tasks:
                    handler = self._handlers.get(task["task_type"])
                    if handler:
                        try:
                            result = await handler(task["user_id"], task["data"])
                            self.db.update_task_status(task["id"], "completed", result=result)
                            logger.info(f"✅ Задача {task['id']} ({task['task_type']}) выполнена")
                        except Exception as e:
                            logger.error(f"❌ Задача {task['id']} провалилась: {e}")
                            self.db.update_task_status(task["id"], "failed", error=str(e))
                    else:
                        logger.warning(f"⚠️ Нет обработчика для {task['task_type']}")
                        self.db.update_task_status(task["id"], "no_handler")
                
                await asyncio.sleep(5)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Ошибка планировщика: {e}")
                await asyncio.sleep(10)
    
    async def schedule_reminder(self, user_id: str, message: str, remind_at: datetime):
        self.db.add_task(user_id, "reminder", {"message": message}, remind_at)
    
    async def schedule_backup(self, interval_hours: int = 24):
        self.db.add_task("system", "backup", {"interval_hours": interval_hours})
    
    async def schedule_daily_summary(self, user_id: str, time: str = "20:00"):
        hour, minute = map(int, time.split(":"))
        now = datetime.now()
        scheduled = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if scheduled <= now:
            scheduled += timedelta(days=1)
        self.db.add_task(user_id, "daily_summary", {}, scheduled)


# ============================================
# ОБРАБОТЧИКИ ЗАДАЧ
# ============================================

async def reminder_handler(user_id: str, data: Dict) -> Dict:
    """Отправляет напоминание пользователю"""
    message = data.get("message", "Напоминание!")
    # Здесь будет интеграция с Telegram/WebSocket
    logger.info(f"🔔 Напоминание для {user_id}: {message}")
    return {"sent": True, "message": message, "timestamp": datetime.now().isoformat()}

async def backup_handler(user_id: str, data: Dict) -> Dict:
    """Создаёт резервную копию"""
    from backup_service import BackupService
    backup = BackupService()
    backup_path = backup.create_backup()
    return {"backup_created": True, "path": backup_path}

async def daily_summary_handler(user_id: str, data: Dict) -> Dict:
    """Отправляет ежедневную сводку"""
    # Анализ активности пользователя
    return {"summary": "Ваша активность за день", "sent": True}


# ============================================
# РЕЗЕРВНОЕ КОПИРОВАНИЕ
# ============================================

class BackupService:
    """Сервис резервного копирования"""
    
    def __init__(self, db: Database):
        self.db = db
    
    def create_backup(self) -> str:
        """Создаёт резервную копию базы данных"""
        backup_path = Config.BACKUP_DIR / f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        shutil.copy2(Config.DATABASE_PATH, backup_path)
        
        # Также копируем все данные пользователей в JSON
        users_backup = Config.BACKUP_DIR / f"users_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        users_data = []
        with sqlite3.connect(Config.DATABASE_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute("SELECT user_id, username, profile, context FROM users")
            for row in cur:
                users_data.append(dict(row))
        
        with open(users_backup, 'w', encoding='utf-8') as f:
            json.dump(users_data, f, ensure_ascii=False, indent=2)
        
        size = backup_path.stat().st_size
        self.db.create_backup()
        
        # Очищаем старые бэкапы (старше 30 дней)
        self._cleanup_old_backups()
        
        return str(backup_path)
    
    def _cleanup_old_backups(self, days: int = 30):
        cutoff = datetime.now().timestamp() - (days * 86400)
        for backup in Config.BACKUP_DIR.glob("*.db"):
            if backup.stat().st_mtime < cutoff:
                backup.unlink()
        for backup in Config.BACKUP_DIR.glob("*.json"):
            if backup.stat().st_mtime < cutoff:
                backup.unlink()
    
    def restore_backup(self, backup_path: str) -> bool:
        """Восстанавливает базу данных из бэкапа"""
        backup_file = Config.BACKUP_DIR / backup_path
        if backup_file.exists():
            shutil.copy2(backup_file, Config.DATABASE_PATH)
            return True
        return False


# ============================================
# СЕРВИС СБОРА ИНФОРМАЦИИ О ГОРОДЕ
# ============================================

class CityInfoService:
    """Собирает информацию о городе из различных источников"""
    
    def __init__(self):
        self.openweather_key = Config.OPENWEATHER_API_KEY
        self.cache: Dict[str, Dict] = {}
    
    async def get_city_info(self, city: str) -> Dict[str, Any]:
        """Получает полную информацию о городе"""
        city_lower = city.lower()
        
        # Проверяем кэш
        if city_lower in self.cache:
            cache_time = self.cache[city_lower].get("cached_at", 0)
            if datetime.now().timestamp() - cache_time < 3600:
                return self.cache[city_lower]["data"]
        
        result = {
            "city": city,
            "weather": await self._get_weather(city),
            "timezone": self._get_timezone(city),
            "transport": self._get_transport_info(city),
            "safety": self._get_safety_info(city),
            "infrastructure": self._get_infrastructure(city),
            "events": await self._get_events(city),
            "recommendations": []
        }
        
        result["recommendations"] = self._generate_recommendations(result)
        
        self.cache[city_lower] = {"data": result, "cached_at": datetime.now().timestamp()}
        return result
    
    async def _get_weather(self, city: str) -> Dict[str, Any]:
        """Получает погоду через OpenWeather API"""
        if not self.openweather_key:
            return {"temperature": "неизвестно", "description": "данные недоступны", "icon": "❓"}
        
        try:
            async with aiohttp.ClientSession() as session:
                url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={self.openweather_key}&units=metric&lang=ru"
                async with session.get(url, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return {
                            "temperature": round(data["main"]["temp"]),
                            "feels_like": round(data["main"]["feels_like"]),
                            "description": data["weather"][0]["description"],
                            "icon": self._get_weather_icon(data["weather"][0]["icon"]),
                            "humidity": data["main"]["humidity"],
                            "wind_speed": data["wind"]["speed"],
                            "pressure": data["main"]["pressure"]
                        }
        except Exception as e:
            logger.error(f"Weather error for {city}: {e}")
        
        return {"temperature": "неизвестно", "description": "погода не определена", "icon": "❓"}
    
    def _get_weather_icon(self, icon_code: str) -> str:
        mapping = {
            "01d": "☀️", "01n": "🌙", "02d": "⛅", "02n": "☁️",
            "03d": "☁️", "03n": "☁️", "04d": "☁️", "04n": "☁️",
            "09d": "🌧️", "09n": "🌧️", "10d": "🌦️", "10n": "🌧️",
            "11d": "⛈️", "11n": "⛈️", "13d": "❄️", "13n": "❄️",
            "50d": "🌫️", "50n": "🌫️"
        }
        return mapping.get(icon_code, "🌡️")
    
    def _get_timezone(self, city: str) -> Dict[str, Any]:
        """Определяет часовой пояс города"""
        timezones = {
            "москва": {"name": "Europe/Moscow", "offset": 3},
            "санкт-петербург": {"name": "Europe/Moscow", "offset": 3},
            "екатеринбург": {"name": "Asia/Yekaterinburg", "offset": 5},
            "новосибирск": {"name": "Asia/Novosibirsk", "offset": 7},
            "владивосток": {"name": "Asia/Vladivostok", "offset": 10},
            "иркутск": {"name": "Asia/Irkutsk", "offset": 8},
            "казань": {"name": "Europe/Moscow", "offset": 3},
            "нижний новгород": {"name": "Europe/Moscow", "offset": 3},
            "самара": {"name": "Europe/Samara", "offset": 4},
            "пермь": {"name": "Asia/Yekaterinburg", "offset": 5},
            "краснодар": {"name": "Europe/Moscow", "offset": 3},
            "сочи": {"name": "Europe/Moscow", "offset": 3},
            "ростов-на-дону": {"name": "Europe/Moscow", "offset": 3}
        }
        
        city_lower = city.lower()
        for city_name, tz in timezones.items():
            if city_name in city_lower:
                return tz
        
        return {"name": "Europe/Moscow", "offset": 3}
    
    def _get_transport_info(self, city: str) -> Dict[str, Any]:
        major_cities = ["москва", "санкт-петербург", "новосибирск", "екатеринбург", "казань", "нижний новгород"]
        is_major = any(c in city.lower() for c in major_cities)
        
        return {
            "has_metro": is_major,
            "has_buses": True,
            "has_trams": is_major,
            "traffic_level": "высокий" if is_major else "средний",
            "peak_hours": ["08:00-10:00", "17:00-19:00"],
            "recommended_alternative": "метро" if is_major else "автобус"
        }
    
    def _get_safety_info(self, city: str) -> Dict[str, Any]:
        return {
            "overall_rating": 7,
            "daytime_safety": 8,
            "night_safety": 6,
            "safe_districts": ["центр", "юго-запад"],
            "unsafe_districts": ["окраины"],
            "recommendations": "В тёмное время суток избегайте неосвещённых улиц"
        }
    
    def _get_infrastructure(self, city: str) -> Dict[str, Any]:
        return {
            "hospitals": "в радиусе 3-5 км",
            "pharmacies": "в шаговой доступности",
            "schools": "в радиусе 1-2 км",
            "parks": "есть",
            "shops": "в шаговой доступности"
        }
    
    async def _get_events(self, city: str) -> List[Dict]:
        # В реальности здесь был бы запрос к API мероприятий
        return [
            {"name": "Выставка современного искусства", "date": "скоро", "type": "culture"},
            {"name": "Фестиваль уличной еды", "date": "выходные", "type": "food"}
        ]
    
    def _generate_recommendations(self, city_info: Dict) -> List[str]:
        recommendations = []
        
        weather = city_info.get("weather", {})
        temp = weather.get("temperature")
        if temp and isinstance(temp, (int, float)):
            if temp < 0:
                recommendations.append("❄️ На улице холодно, одевайтесь теплее")
            elif temp > 25:
                recommendations.append("☀️ Жарко, не забывайте пить воду")
            elif "дождь" in weather.get("description", "").lower():
                recommendations.append("🌧️ Возьмите зонт, ожидается дождь")
        
        transport = city_info.get("transport", {})
        if transport.get("traffic_level") == "высокий":
            recommendations.append("🚗 В часы пик лучше пользоваться общественным транспортом")
        
        return recommendations


# ============================================
# СЕРВИС РАБОТЫ С GITHUB
# ============================================

class GitHubService:
    """Создаёт и изменяет файлы в репозитории GitHub"""
    
    def __init__(self):
        self.token = Config.GITHUB_TOKEN
        self.repo = Config.GITHUB_REPO
        self.api_base = "https://api.github.com/repos"
    
    async def create_file(self, path: str, content: str, commit_message: str) -> Dict:
        """Создаёт новый файл в репозитории"""
        if not self.token:
            return {"success": False, "error": "GitHub token not configured"}
        
        url = f"{self.api_base}/{self.repo}/contents/{path}"
        content_base64 = base64.b64encode(content.encode()).decode()
        
        async with aiohttp.ClientSession() as session:
            async with session.put(
                url,
                headers={
                    "Authorization": f"token {self.token}",
                    "Accept": "application/vnd.github.v3+json"
                },
                json={
                    "message": commit_message,
                    "content": content_base64,
                    "branch": "main"
                }
            ) as resp:
                if resp.status in [200, 201]:
                    data = await resp.json()
                    return {"success": True, "path": path, "url": data.get("content", {}).get("html_url")}
                else:
                    error = await resp.text()
                    return {"success": False, "error": error}
    
    async def update_file(self, path: str, content: str, commit_message: str) -> Dict:
        """Обновляет существующий файл"""
        if not self.token:
            return {"success": False, "error": "GitHub token not configured"}
        
        url = f"{self.api_base}/{self.repo}/contents/{path}"
        
        async with aiohttp.ClientSession() as session:
            # Получаем текущий файл для SHA
            async with session.get(
                url,
                headers={"Authorization": f"token {self.token}"}
            ) as resp:
                if resp.status != 200:
                    return {"success": False, "error": "File not found"}
                data = await resp.json()
                sha = data.get("sha")
            
            content_base64 = base64.b64encode(content.encode()).decode()
            async with session.put(
                url,
                headers={"Authorization": f"token {self.token}"},
                json={
                    "message": commit_message,
                    "content": content_base64,
                    "sha": sha,
                    "branch": "main"
                }
            ) as resp:
                if resp.status in [200, 201]:
                    return {"success": True, "path": path}
                else:
                    error = await resp.text()
                    return {"success": False, "error": error}
    
    async def create_app(self, app_name: str, app_type: str, description: str) -> Dict:
        """Создаёт новое приложение на основе шаблона"""
        templates = {
            "telegram_bot": self._generate_telegram_bot_template,
            "web_app": self._generate_web_app_template,
            "api": self._generate_api_template,
            "cli": self._generate_cli_template
        }
        
        generator = templates.get(app_type, self._generate_web_app_template)
        content = generator(app_name, description)
        
        path = f"apps/{app_name}/main.py"
        return await self.create_file(path, content, f"Create {app_name} ({app_type})")
    
    def _generate_telegram_bot_template(self, name: str, description: str) -> str:
        return f'''#!/usr/bin/env python3
"""
{name} - Telegram Bot
{description}
"""

import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("BOT_TOKEN", "YOUR_TOKEN_HERE")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я {name}.\\n\\n{description}\\n\\n"
        "Используй /help для списка команд."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Доступные команды:\\n"
        "/start - Начать диалог\\n"
        "/help - Показать справку"
    )

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    await update.message.reply_text(f"Вы сказали: {{text}}")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
    logger.info("Бот запущен")
    app.run_polling()

if __name__ == "__main__":
    main()
'''
    
    def _generate_web_app_template(self, name: str, description: str) -> str:
        return f'''#!/usr/bin/env python3
"""
{name} - Web Application
{description}
"""

from fastapi import FastAPI
import uvicorn

app = FastAPI(title="{name}", description="{description}")

@app.get("/")
async def root():
    return {{"name": "{name}", "status": "running", "description": "{description}"}}

@app.get("/health")
async def health():
    return {{"status": "ok"}}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
'''
    
    def _generate_api_template(self, name: str, description: str) -> str:
        return f'''#!/usr/bin/env python3
"""
{name} - API Service
{description}
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, Optional
import uvicorn

app = FastAPI(title="{name}", description="{description}")

class RequestModel(BaseModel):
    data: Dict[str, Any]

class ResponseModel(BaseModel):
    success: bool
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

@app.post("/api/process", response_model=ResponseModel)
async def process_request(request: RequestModel):
    try:
        result = {{"received": request.data, "processed": True}}
        return ResponseModel(success=True, result=result)
    except Exception as e:
        return ResponseModel(success=False, error=str(e))

@app.get("/health")
async def health():
    return {{"status": "ok"}}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
'''
    
    def _generate_cli_template(self, name: str, description: str) -> str:
        return f'''#!/usr/bin/env python3
"""
{name} - Command Line Tool
{description}
"""

import argparse

def main():
    parser = argparse.ArgumentParser(description="{description}")
    parser.add_argument("--input", "-i", help="Входной файл")
    parser.add_argument("--output", "-o", help="Выходной файл")
    parser.add_argument("--verbose", "-v", action="store_true", help="Подробный вывод")
    
    args = parser.parse_args()
    
    if args.verbose:
        print(f"Запуск {name}")
    
    if args.input:
        print(f"Обработка файла: {{args.input}}")
    
    print("Готово!")

if __name__ == "__main__":
    main()
'''


# ============================================
# AI СЕРВИС (DeepSeek)
# ============================================

class AIService:
    """Сервис для работы с DeepSeek API"""
    
    def __init__(self):
        self.api_key = Config.DEEPSEEK_API_KEY
        self.api_url = "https://api.deepseek.com/v1/chat/completions"
    
    async def chat(self, messages: List[Dict], temperature: float = 0.7) -> str:
        if not self.api_key:
            return "AI сервис временно недоступен. Пожалуйста, попробуйте позже."
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.api_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "deepseek-chat",
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": 2000
                },
                timeout=30
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data["choices"][0]["message"]["content"]
                else:
                    logger.error(f"AI API error: {resp.status}")
                    return "Извините, произошла ошибка. Попробуйте позже."
    
    async def analyze_user(self, conversation: List[Dict]) -> Dict:
        system_prompt = """Ты психолог, анализирующий диалог с пользователем.
Определи его психологический профиль по системе Вариатика (4 масти: СБ, ТФ, УБ, ЧВ).
Каждая масть оценивается от 1 до 6.

Верни ТОЛЬКО JSON в формате:
{
  "СБ": число от 1 до 6,
  "ТФ": число от 1 до 6,
  "УБ": число от 1 до 6,
  "ЧВ": число от 1 до 6,
  "perception_type": "один из: СОЦИАЛЬНО-ОРИЕНТИРОВАННЫЙ, СТАТУСНО-ОРИЕНТИРОВАННЫЙ, СМЫСЛО-ОРИЕНТИРОВАННЫЙ, ПРАКТИКО-ОРИЕНТИРОВАННЫЙ",
  "thinking_level": число от 1 до 9,
  "dominant": "СБ/ТФ/УБ/ЧВ"
}"""
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(conversation[-20:], ensure_ascii=False)}
        ]
        
        response = await self.chat(messages, temperature=0.3)
        
        json_match = re.search(r'\{[^{}]*\}', response, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group())
            except:
                pass
        
        return {"СБ": 3, "ТФ": 3, "УБ": 3, "ЧВ": 3, "perception_type": "СОЦИАЛЬНО-ОРИЕНТИРОВАННЫЙ", "thinking_level": 5, "dominant": "ЧВ"}
    
    async def generate_response(self, user_message: str, profile: Dict, context: Dict, conversation: List[Dict]) -> str:
        system_prompt = f"""Ты Фреди, виртуальный помощник.

ПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ:
- Доминантная масть: {profile.get('dominant', 'ЧВ')}
- Уровни: СБ={profile.get('СБ', 3)}, ТФ={profile.get('ТФ', 3)}, УБ={profile.get('УБ', 3)}, ЧВ={profile.get('ЧВ', 3)}
- Тип восприятия: {profile.get('perception_type', 'не определён')}
- Уровень мышления: {profile.get('thinking_level', 5)}/9

КОНТЕКСТ:
- Город: {context.get('city', 'не указан')}
- Погода: {context.get('weather', {}).get('description', '')}

Ты можешь:
- Создавать приложения (Telegram боты, веб-приложения, API, CLI)
- Анализировать код
- Давать рекомендации
- Отвечать на вопросы

Отвечай на русском, обращайся на «ты». Будь полезным и эмпатичным."""
        
        messages = [
            {"role": "system", "content": system_prompt},
            *conversation[-10:],
            {"role": "user", "content": user_message}
        ]
        
        return await self.chat(messages)


# ============================================
# ГОЛОСОВОЙ СЕРВИС
# ============================================

class VoiceService:
    def __init__(self):
        self.yandex_key = Config.YANDEX_API_KEY
    
    async def speech_to_text(self, audio_bytes: bytes, format: str = "ogg") -> str:
        if not self.yandex_key:
            return None
        
        try:
            async with aiohttp.ClientSession() as session:
                url = "https://stt.api.cloud.yandex.net/speech/v1/stt:recognize"
                headers = {"Authorization": f"Api-Key {self.yandex_key}"}
                
                async with session.post(url, headers=headers, data=audio_bytes, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("result", "")
        except Exception as e:
            logger.error(f"STT error: {e}")
        
        return None
    
    async def text_to_speech(self, text: str, voice: str = "jane") -> bytes:
        if not self.yandex_key:
            return None
        
        try:
            async with aiohttp.ClientSession() as session:
                url = "https://tts.api.cloud.yandex.net/speech/v1/tts:synthesize"
                headers = {"Authorization": f"Api-Key {self.yandex_key}"}
                data = {
                    "text": text[:500],
                    "voice": voice,
                    "emotion": "neutral",
                    "speed": 1.0,
                    "format": "oggopus"
                }
                
                async with session.post(url, headers=headers, data=data, timeout=10) as resp:
                    if resp.status == 200:
                        return await resp.read()
        except Exception as e:
            logger.error(f"TTS error: {e}")
        
        return None


# ============================================
# СОСТОЯНИЕ ПОЛЬЗОВАТЕЛЯ
# ============================================

class UserState:
    def __init__(self, user_id: str, db: Database):
        self.user_id = user_id
        self.db = db
        self._load()
    
    def _load(self):
        user = self.db.get_user(self.user_id)
        if user:
            self.profile = json.loads(user.get("profile", "{}")) if user.get("profile") else {}
            self.context = json.loads(user.get("context", "{}")) if user.get("context") else {}
            self.settings = json.loads(user.get("settings", "{}")) if user.get("settings") else {}
        else:
            self.profile = {}
            self.context = {}
            self.settings = {}
    
    def save(self):
        self.db.update_user_profile(self.user_id, self.profile)
        self.db.update_user_context(self.user_id, self.context)
        self.db.update_user_settings(self.user_id, self.settings)
    
    def add_message(self, role: str, content: str, metadata: Dict = None):
        self.db.add_message(self.user_id, role, content, metadata)
    
    def get_history(self, limit: int = 50) -> List[Dict]:
        return self.db.get_history(self.user_id, limit)


# ============================================
# HTML ИНТЕРФЕЙС
# ============================================

HTML_TEMPLATE = '''<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
    <title>Фреди - AI Помощник</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            color: #fff;
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
            height: 100vh;
            display: flex;
            flex-direction: column;
            padding: 20px;
        }
        
        .header {
            text-align: center;
            padding: 20px;
            border-bottom: 1px solid rgba(255,255,255,0.1);
            margin-bottom: 20px;
        }
        
        .header h1 {
            font-size: 24px;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 10px;
        }
        
        .status {
            font-size: 12px;
            color: #4ade80;
            margin-top: 5px;
        }
        
        .chat-container {
            flex: 1;
            overflow-y: auto;
            padding: 20px;
            background: rgba(255,255,255,0.05);
            border-radius: 20px;
            margin-bottom: 20px;
        }
        
        .message {
            margin-bottom: 15px;
            display: flex;
        }
        
        .message.user {
            justify-content: flex-end;
        }
        
        .message.bot {
            justify-content: flex-start;
        }
        
        .message-bubble {
            max-width: 70%;
            padding: 12px 16px;
            border-radius: 20px;
            word-wrap: break-word;
        }
        
        .message.user .message-bubble {
            background: linear-gradient(135deg, #6366f1, #8b5cf6);
            border-bottom-right-radius: 5px;
        }
        
        .message.bot .message-bubble {
            background: rgba(255,255,255,0.1);
            border-bottom-left-radius: 5px;
        }
        
        .message-time {
            font-size: 10px;
            color: rgba(255,255,255,0.4);
            margin-top: 5px;
        }
        
        .input-panel {
            display: flex;
            gap: 10px;
            padding: 10px;
            background: rgba(255,255,255,0.05);
            border-radius: 30px;
        }
        
        .input-panel input {
            flex: 1;
            padding: 15px 20px;
            border: none;
            border-radius: 30px;
            background: rgba(255,255,255,0.1);
            color: white;
            font-size: 16px;
            outline: none;
        }
        
        .input-panel input::placeholder {
            color: rgba(255,255,255,0.5);
        }
        
        .btn {
            padding: 15px 25px;
            border: none;
            border-radius: 30px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
        }
        
        .btn-send {
            background: linear-gradient(135deg, #6366f1, #8b5cf6);
            color: white;
        }
        
        .btn-voice {
            background: rgba(255,255,255,0.1);
            color: white;
        }
        
        .btn-voice.recording {
            background: #ef4444;
            animation: pulse 1s infinite;
        }
        
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.7; }
        }
        
        .btn:hover {
            transform: scale(1.02);
        }
        
        .typing-indicator {
            display: flex;
            gap: 5px;
            padding: 10px 15px;
            background: rgba(255,255,255,0.1);
            border-radius: 20px;
            width: fit-content;
        }
        
        .typing-indicator span {
            width: 8px;
            height: 8px;
            background: white;
            border-radius: 50%;
            animation: typing 1.4s infinite;
        }
        
        .typing-indicator span:nth-child(2) { animation-delay: 0.2s; }
        .typing-indicator span:nth-child(3) { animation-delay: 0.4s; }
        
        @keyframes typing {
            0%, 60%, 100% { transform: translateY(0); opacity: 0.5; }
            30% { transform: translateY(-10px); opacity: 1; }
        }
        
        .auth-panel {
            display: flex;
            gap: 10px;
            justify-content: center;
            margin-bottom: 20px;
        }
        
        .auth-btn {
            padding: 10px 20px;
            background: rgba(255,255,255,0.1);
            border: none;
            border-radius: 20px;
            color: white;
            cursor: pointer;
        }
        
        .auth-btn.active {
            background: linear-gradient(135deg, #6366f1, #8b5cf6);
        }
        
        .modal {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.8);
            justify-content: center;
            align-items: center;
            z-index: 1000;
        }
        
        .modal-content {
            background: #1a1a2e;
            padding: 30px;
            border-radius: 20px;
            width: 90%;
            max-width: 400px;
        }
        
        .modal-content input {
            width: 100%;
            padding: 12px;
            margin: 10px 0;
            background: rgba(255,255,255,0.1);
            border: 1px solid rgba(255,255,255,0.2);
            border-radius: 10px;
            color: white;
        }
        
        .modal-content button {
            width: 100%;
            padding: 12px;
            margin-top: 10px;
            background: linear-gradient(135deg, #6366f1, #8b5cf6);
            border: none;
            border-radius: 10px;
            color: white;
            cursor: pointer;
        }
        
        @media (max-width: 768px) {
            .container { padding: 10px; }
            .message-bubble { max-width: 85%; }
            .btn { padding: 12px 20px; }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>
                <span>🧠</span>
                <span>Фреди</span>
                <span>🤖</span>
            </h1>
            <div class="status" id="status">● Готов к работе</div>
        </div>
        
        <div class="auth-panel" id="authPanel">
            <button class="auth-btn" onclick="showLogin()">Вход</button>
            <button class="auth-btn" onclick="showRegister()">Регистрация</button>
        </div>
        
        <div class="chat-container" id="chatContainer">
            <div class="message bot">
                <div class="message-bubble">
                    Привет! Я Фреди — твой автономный AI-помощник.<br><br>
                    Я могу:<br>
                    • 💬 Отвечать на вопросы<br>
                    • 🎙️ Распознавать голос<br>
                    • 📝 Создавать приложения<br>
                    • 🌍 Анализировать города<br>
                    • ⏰ Напоминать о задачах<br>
                    • 💾 Сохранять всю историю<br><br>
                    <b>Войдите или зарегистрируйтесь, чтобы начать!</b>
                    <div class="message-time">только что</div>
                </div>
            </div>
        </div>
        
        <div class="input-panel">
            <input type="text" id="messageInput" placeholder="Напишите сообщение..." autocomplete="off" disabled>
            <button class="btn btn-voice" id="voiceBtn" disabled>🎤</button>
            <button class="btn btn-send" id="sendBtn" disabled>📤</button>
        </div>
    </div>
    
    <div id="loginModal" class="modal">
        <div class="modal-content">
            <h3>Вход</h3>
            <input type="text" id="loginUsername" placeholder="Имя пользователя">
            <input type="password" id="loginPassword" placeholder="Пароль">
            <button onclick="doLogin()">Войти</button>
            <button onclick="closeModal('loginModal')">Отмена</button>
        </div>
    </div>
    
    <div id="registerModal" class="modal">
        <div class="modal-content">
            <h3>Регистрация</h3>
            <input type="text" id="regUsername" placeholder="Имя пользователя">
            <input type="email" id="regEmail" placeholder="Email">
            <input type="password" id="regPassword" placeholder="Пароль">
            <button onclick="doRegister()">Зарегистрироваться</button>
            <button onclick="closeModal('registerModal')">Отмена</button>
        </div>
    </div>
    
    <script>
        let token = localStorage.getItem('token');
        let userId = localStorage.getItem('user_id');
        let isRecording = false;
        let mediaRecorder = null;
        let audioChunks = [];
        
        const chatContainer = document.getElementById('chatContainer');
        const messageInput = document.getElementById('messageInput');
        const sendBtn = document.getElementById('sendBtn');
        const voiceBtn = document.getElementById('voiceBtn');
        const statusEl = document.getElementById('status');
        
        function showLogin() {
            document.getElementById('loginModal').style.display = 'flex';
        }
        
        function showRegister() {
            document.getElementById('registerModal').style.display = 'flex';
        }
        
        function closeModal(id) {
            document.getElementById(id).style.display = 'none';
        }
        
        async function doLogin() {
            const username = document.getElementById('loginUsername').value;
            const password = document.getElementById('loginPassword').value;
            
            const response = await fetch('/api/auth/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password })
            });
            
            const data = await response.json();
            if (data.success) {
                token = data.token;
                localStorage.setItem('token', token);
                localStorage.setItem('user_id', data.user_id);
                userId = data.user_id;
                closeModal('loginModal');
                enableChat();
                loadHistory();
                statusEl.textContent = '● Вы вошли как ' + username;
            } else {
                alert('Ошибка входа: ' + data.error);
            }
        }
        
        async function doRegister() {
            const username = document.getElementById('regUsername').value;
            const email = document.getElementById('regEmail').value;
            const password = document.getElementById('regPassword').value;
            
            const response = await fetch('/api/auth/register', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, email, password })
            });
            
            const data = await response.json();
            if (data.success) {
                alert('Регистрация успешна! Теперь войдите.');
                closeModal('registerModal');
            } else {
                alert('Ошибка регистрации: ' + data.error);
            }
        }
        
        function enableChat() {
            messageInput.disabled = false;
            sendBtn.disabled = false;
            voiceBtn.disabled = false;
        }
        
        function addMessage(text, isUser = false) {
            const messageDiv = document.createElement('div');
            messageDiv.className = `message ${isUser ? 'user' : 'bot'}`;
            messageDiv.innerHTML = `
                <div class="message-bubble">
                    ${text.replace(/\\n/g, '<br>')}
                    <div class="message-time">${new Date().toLocaleTimeString()}</div>
                </div>
            `;
            chatContainer.appendChild(messageDiv);
            chatContainer.scrollTop = chatContainer.scrollHeight;
        }
        
        function showTyping() {
            const typingDiv = document.createElement('div');
            typingDiv.className = 'message bot';
            typingDiv.id = 'typingIndicator';
            typingDiv.innerHTML = `
                <div class="message-bubble">
                    <div class="typing-indicator">
                        <span></span><span></span><span></span>
                    </div>
                </div>
            `;
            chatContainer.appendChild(typingDiv);
            chatContainer.scrollTop = chatContainer.scrollHeight;
        }
        
        function hideTyping() {
            const typing = document.getElementById('typingIndicator');
            if (typing) typing.remove();
        }
        
        async function sendMessage(text, isVoice = false) {
            if (!text.trim() || !token) return;
            
            addMessage(text, true);
            messageInput.value = '';
            showTyping();
            statusEl.textContent = '● Думаю...';
            
            try {
                const response = await fetch('/api/chat', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${token}`
                    },
                    body: JSON.stringify({
                        user_id: userId,
                        message: text,
                        is_voice: isVoice
                    })
                });
                
                const data = await response.json();
                hideTyping();
                
                if (data.success) {
                    addMessage(data.response);
                    
                    if (data.audio_base64) {
                        const audio = new Audio('data:audio/mpeg;base64,' + data.audio_base64);
                        audio.play();
                    }
                } else {
                    addMessage('❌ ' + (data.error || 'Ошибка'));
                }
                
                statusEl.textContent = '● Готов к работе';
            } catch (error) {
                hideTyping();
                addMessage('❌ Ошибка соединения');
                statusEl.textContent = '● Ошибка';
                console.error(error);
            }
        }
        
        async function loadHistory() {
            if (!token) return;
            
            try {
                const response = await fetch(`/api/chat/history/${userId}`, {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                const data = await response.json();
                if (data.success && data.history) {
                    for (const msg of data.history) {
                        addMessage(msg.content, msg.role === 'user');
                    }
                }
            } catch (error) {
                console.error('History load error:', error);
            }
        }
        
        async function startRecording() {
            try {
                const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
                audioChunks = [];
                
                mediaRecorder.ondataavailable = (event) => {
                    audioChunks.push(event.data);
                };
                
                mediaRecorder.onstop = async () => {
                    const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
                    const formData = new FormData();
                    formData.append('user_id', userId);
                    formData.append('voice', audioBlob, 'recording.webm');
                    
                    statusEl.textContent = '● Распознаю...';
                    showTyping();
                    
                    try {
                        const response = await fetch('/api/voice/process', {
                            method: 'POST',
                            headers: { 'Authorization': `Bearer ${token}` },
                            body: formData
                        });
                        
                        const data = await response.json();
                        hideTyping();
                        
                        if (data.success && data.recognized_text) {
                            addMessage(data.recognized_text, true);
                            addMessage(data.answer);
                            
                            if (data.audio_base64) {
                                const audio = new Audio('data:audio/mpeg;base64,' + data.audio_base64);
                                audio.play();
                            }
                        } else {
                            addMessage('❌ Не удалось распознать речь');
                        }
                    } catch (error) {
                        hideTyping();
                        addMessage('❌ Ошибка голосового распознавания');
                    }
                    
                    statusEl.textContent = '● Готов к работе';
                    stream.getTracks().forEach(track => track.stop());
                    voiceBtn.classList.remove('recording');
                    isRecording = false;
                };
                
                mediaRecorder.start();
                voiceBtn.classList.add('recording');
                isRecording = true;
                statusEl.textContent = '● Запись...';
                
                setTimeout(() => {
                    if (isRecording) stopRecording();
                }, 30000);
                
            } catch (error) {
                console.error('Microphone error:', error);
                addMessage('❌ Не удалось получить доступ к микрофону');
                statusEl.textContent = '● Ошибка микрофона';
            }
        }
        
        function stopRecording() {
            if (mediaRecorder && isRecording) {
                mediaRecorder.stop();
            }
        }
        
        voiceBtn.onmousedown = startRecording;
        voiceBtn.onmouseup = stopRecording;
        voiceBtn.ontouchend = stopRecording;
        
        sendBtn.onclick = () => sendMessage(messageInput.value);
        messageInput.onkeypress = (e) => {
            if (e.key === 'Enter') sendMessage(messageInput.value);
        };
        
        if (token) {
            enableChat();
            loadHistory();
        }
    </script>
</body>
</html>
'''


# ============================================
# FASTAPI ПРИЛОЖЕНИЕ
# ============================================

# Инициализация компонентов
db = Database()
auth = AuthManager(db)
scheduler = TaskScheduler(db)
backup_service = BackupService(db)
city_service = CityInfoService()
github_service = GitHubService()
ai_service = AIService()
voice_service = VoiceService()

# Регистрация обработчиков задач
scheduler.register_handler("reminder", reminder_handler)
scheduler.register_handler("backup", backup_handler)
scheduler.register_handler("daily_summary", daily_summary_handler)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом"""
    logger.info(f"🚀 Запуск {Config.APP_NAME} v{Config.APP_VERSION}")
    
    # Запуск планировщика
    await scheduler.start()
    
    # Планируем ежедневный бэкап
    scheduler.schedule_backup(24)
    
    yield
    
    # Остановка
    await scheduler.stop()
    logger.info(f"🛑 Остановка {Config.APP_NAME}")


app = FastAPI(
    title=Config.APP_NAME,
    description="Автономный AI-помощник",
    version=Config.APP_VERSION,
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://agent-frontend-fxtv.onrender.com",
        "https://agent-frontend.onrender.com",
        "https://agent-ynlg.onrender.com",
        "http://localhost:3000",
        "http://localhost:8000",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8000",
    ],
    allow_origin_regex=r"https?://(.*\.onrender\.com|localhost(:\d+)?|127\.0\.0\.1(:\d+)?)",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=600,
)


# ============================================
# MIDDLEWARE АУТЕНТИФИКАЦИИ
# ============================================

async def get_current_user(authorization: Optional[str] = None):
    """Получает текущего пользователя из токена"""
    if not authorization:
        return None
    
    scheme, _, token = authorization.partition(' ')
    if scheme.lower() != 'bearer':
        return None
    
    user_id = auth.verify_token(token)
    return user_id


# ============================================
# ЭНДПОИНТЫ
# ============================================

@app.get("/")
async def root():
    """Главная страница"""
    return HTMLResponse(HTML_TEMPLATE)


@app.get("/health")
async def health():
    """Проверка здоровья"""
    return {
        "status": "ok",
        "version": Config.APP_VERSION,
        "services": {
            "database": True,
            "ai": bool(Config.DEEPSEEK_API_KEY),
            "voice": bool(Config.YANDEX_API_KEY),
            "weather": bool(Config.OPENWEATHER_API_KEY),
            "github": bool(Config.GITHUB_TOKEN)
        }
    }


# ============================================
# АУТЕНТИФИКАЦИЯ
# ============================================

class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str


@app.post("/api/auth/register")
async def register(request: RegisterRequest):
    """Регистрация пользователя"""
    result = auth.register(request.username, request.email, request.password)
    if result:
        return {"success": True, "user": result}
    return {"success": False, "error": "Пользователь уже существует"}


@app.post("/api/auth/login")
async def login(request: LoginRequest):
    """Вход пользователя"""
    token = auth.login(request.username, request.password)
    if token:
        user = db.get_user_by_username(request.username)
        return {"success": True, "token": token, "user_id": user["user_id"]}
    return {"success": False, "error": "Неверные имя пользователя или пароль"}


@app.post("/api/auth/logout")
async def logout(authorization: str = None):
    """Выход пользователя"""
    if authorization:
        scheme, _, token = authorization.partition(' ')
        if scheme.lower() == 'bearer':
            auth.logout(token)
    return {"success": True}


# ============================================
# ОСНОВНЫЕ ЭНДПОИНТЫ
# ============================================

class ChatRequest(BaseModel):
    user_id: str
    message: str
    is_voice: bool = False


@app.post("/api/chat")
async def chat(request: ChatRequest, authorization: str = None):
    """Обработка сообщения"""
    # Проверка авторизации
    user_id_from_token = await get_current_user(authorization)
    if not user_id_from_token or user_id_from_token != request.user_id:
        return {"success": False, "error": "Не авторизован"}
    
    try:
        state = UserState(request.user_id, db)
        state.add_message("user", request.message)
        
        # Анализ профиля если нужно
        if not state.profile and len(state.get_history()) >= 10:
            profile = await ai_service.analyze_user(state.get_history())
            state.profile = profile
            state.save()
        
        # Определяем город
        city_match = re.search(r'(?:в|из|во)\s+([А-Я][а-я]+(?:-?[А-Я][а-я]+)?)', request.message)
        if city_match and not state.context.get("city"):
            city = city_match.group(1)
            state.context["city"] = city
            city_info = await city_service.get_city_info(city)
            state.context["weather"] = city_info.get("weather", {})
            state.save()
        
        # Генерация ответа
        response = await ai_service.generate_response(
            request.message,
            state.profile,
            state.context,
            state.get_history()
        )
        
        # Создание приложения если нужно
        if any(keyword in request.message.lower() for keyword in ["создай приложение", "сделай бота", "напиши код"]):
            app_name_match = re.search(r'["\']?([А-Яа-яA-Za-z0-9_]+)', request.message)
            app_type = "web_app"
            if "телеграм" in request.message.lower() or "telegram" in request.message.lower():
                app_type = "telegram_bot"
            elif "api" in request.message.lower():
                app_type = "api"
            elif "cli" in request.message.lower():
                app_type = "cli"
            
            app_name = app_name_match.group(1) if app_name_match else f"app_{int(datetime.now().timestamp())}"
            
            result = await github_service.create_app(app_name, app_type, request.message[:100])
            if result.get("success"):
                response += f"\n\n✅ Приложение **{app_name}** создано!\n📁 Путь: `{result.get('path')}`"
                db.add_repository(request.user_id, app_name, result.get("url", ""))
        
        # Напоминания
        reminder_match = re.search(r'(?:напомни|запланируй)\s+(.+?)\s+(?:в|на)\s+(\d{1,2}:\d{2})', request.message.lower())
        if reminder_match:
            message = reminder_match.group(1)
            time_str = reminder_match.group(2)
            hour, minute = map(int, time_str.split(':'))
            remind_at = datetime.now().replace(hour=hour, minute=minute, second=0, microsecond=0)
            if remind_at <= datetime.now():
                remind_at += timedelta(days=1)
            await scheduler.schedule_reminder(request.user_id, message, remind_at)
            response += f"\n\n🔔 Напомню в {time_str}: {message}"
        
        state.add_message("assistant", response)
        state.save()
        
        return {"success": True, "response": response}
        
    except Exception as e:
        logger.error(f"Chat error: {e}")
        return {"success": False, "error": str(e)}


@app.post("/api/voice/process")
async def process_voice(
    user_id: str = Form(...),
    voice: UploadFile = File(...),
    authorization: str = None
):
    """Обработка голоса"""
    user_id_from_token = await get_current_user(authorization)
    if not user_id_from_token or user_id_from_token != user_id:
        return {"success": False, "error": "Не авторизован"}
    
    try:
        audio_bytes = await voice.read()
        if len(audio_bytes) < 1000:
            return {"success": False, "error": "Аудио слишком короткое"}
        
        recognized_text = await voice_service.speech_to_text(audio_bytes)
        if not recognized_text:
            return {"success": False, "error": "Не удалось распознать речь"}
        
        # Обработка как обычного сообщения
        state = UserState(user_id, db)
        state.add_message("user", recognized_text)
        
        response = await ai_service.generate_response(
            recognized_text,
            state.profile,
            state.context,
            state.get_history()
        )
        
        state.add_message("assistant", response)
        state.save()
        
        audio_response = await voice_service.text_to_speech(response[:500])
        
        return {
            "success": True,
            "recognized_text": recognized_text,
            "answer": response,
            "audio_base64": base64.b64encode(audio_response).decode() if audio_response else None
        }
        
    except Exception as e:
        logger.error(f"Voice error: {e}")
        return {"success": False, "error": str(e)}


@app.get("/api/chat/history/{user_id}")
async def get_history(user_id: str, limit: int = 50, authorization: str = None):
    """История диалога"""
    user_id_from_token = await get_current_user(authorization)
    if not user_id_from_token or user_id_from_token != user_id:
        return {"success": False, "error": "Не авторизован"}
    
    state = UserState(user_id, db)
    history = state.get_history(limit)
    return {"success": True, "history": history}


@app.get("/api/user/profile/{user_id}")
async def get_user_profile(user_id: str, authorization: str = None):
    """Профиль пользователя"""
    user_id_from_token = await get_current_user(authorization)
    if not user_id_from_token or user_id_from_token != user_id:
        return {"success": False, "error": "Не авторизован"}
    
    state = UserState(user_id, db)
    return {"success": True, "profile": state.profile, "context": state.context}


@app.get("/api/city/info/{city}")
async def get_city_info(city: str):
    """Информация о городе"""
    info = await city_service.get_city_info(city)
    return {"success": True, "info": info}


@app.post("/api/reminder")
async def create_reminder(
    user_id: str,
    message: str,
    remind_at: str,
    authorization: str = None
):
    """Создание напоминания"""
    user_id_from_token = await get_current_user(authorization)
    if not user_id_from_token or user_id_from_token != user_id:
        return {"success": False, "error": "Не авторизован"}
    
    remind_dt = datetime.fromisoformat(remind_at)
    await scheduler.schedule_reminder(user_id, message, remind_dt)
    return {"success": True}


@app.post("/api/backup")
async def create_backup(authorization: str = None):
    """Создание резервной копии"""
    if not authorization:
        return {"success": False, "error": "Требуется авторизация"}
    
    user_id = await get_current_user(authorization)
    if not user_id:
        return {"success": False, "error": "Не авторизован"}
    
    backup_path = backup_service.create_backup()
    return {"success": True, "backup_path": backup_path}


@app.get("/api/backups")
async def get_backups(authorization: str = None):
    """Список бэкапов"""
    if not authorization:
        return {"success": False, "error": "Требуется авторизация"}
    
    user_id = await get_current_user(authorization)
    if not user_id:
        return {"success": False, "error": "Не авторизован"}
    
    backups = db.get_backups()
    return {"success": True, "backups": backups}


@app.post("/api/restore/{backup_name}")
async def restore_backup(backup_name: str, authorization: str = None):
    """Восстановление из бэкапа"""
    if not authorization:
        return {"success": False, "error": "Требуется авторизация"}
    
    user_id = await get_current_user(authorization)
    if not user_id:
        return {"success": False, "error": "Не авторизован"}
    
    result = backup_service.restore_backup(backup_name)
    return {"success": result}


@app.get("/api/repositories/{user_id}")
async def get_repositories(user_id: str, authorization: str = None):
    """Список репозиториев пользователя"""
    user_id_from_token = await get_current_user(authorization)
    if not user_id_from_token or user_id_from_token != user_id:
        return {"success": False, "error": "Не авторизован"}
    
    repos = db.get_repositories(user_id)
    return {"success": True, "repositories": repos}


# ============================================
# ЗАПУСК
# ============================================

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=Config.PORT, log_level="info")
