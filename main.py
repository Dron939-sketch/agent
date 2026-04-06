#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Фреди - Виртуальный психолог и AI-агент
Версия 4.0 - Агентная система с созданием приложений и сбором данных о городе
"""

import os
import sys
import asyncio
import logging
import json
import base64
import re
import subprocess
import tempfile
import shutil
from datetime import datetime
from contextlib import asynccontextmanager
from typing import Optional, Dict, Any, List, Tuple
from pathlib import Path

from fastapi import FastAPI, Request, HTTPException, WebSocket, WebSocketDisconnect, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn
import aiohttp
import aiofiles

# ============================================
# ЛОГИРОВАНИЕ
# ============================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================
# КОНФИГУРАЦИЯ
# ============================================
class Config:
    GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
    GITHUB_REPO = os.environ.get("GITHUB_REPO", "your-username/your-repo")
    OPENWEATHER_API_KEY = os.environ.get("OPENWEATHER_API_KEY", "")
    DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
    YANDEX_API_KEY = os.environ.get("YANDEX_API_KEY", "")
    
    # Пути
    BASE_DIR = Path(__file__).parent
    STATIC_DIR = BASE_DIR / "static"
    REPO_DIR = BASE_DIR / "github_repo"
    LOGS_DIR = BASE_DIR / "logs"

# Создаём директории
Config.STATIC_DIR.mkdir(exist_ok=True)
Config.REPO_DIR.mkdir(exist_ok=True)
Config.LOGS_DIR.mkdir(exist_ok=True)

# ============================================
# БАЗА ЗНАНИЙ ВАРИАТИКИ
# ============================================

VARITYPE_KB = {
    "version": "2.0",
    "mapping": {1: 6, 2: 7, 3: 8, 4: 9, 5: 10, 6: 11},
    "level_names": {6: "Шестёрка", 7: "Семёрка", 8: "Восьмёрка", 9: "Девятка", 10: "Десятка", 11: "Мастер"},
    
    "vectors": {
        "СБ": {
            "name": "Силовик",
            "essence": "Выживает через контроль силы",
            "core_fear": "Физическая боль, унижение, слабость",
            "core_need": "Безопасность и уважение через силу",
            "communication": {"preference": "Кратко, прямо, по делу", "message_format": "Команды, чек-листы", "what_to_avoid": "Долгих объяснений"},
            "levels": {
                1: {"name": "Шестёрка — Жертва", "what_they_need": "Научиться говорить «нет»", "how_to_lead": "Не давить, мягко укреплять границы"},
                2: {"name": "Семёрка — Избегающий", "what_they_need": "Понять, что избегание не решает проблемы", "how_to_lead": "Показывать, что конфликты неизбежны"},
                3: {"name": "Восьмёрка — Провокатор", "what_they_need": "Научиться контролировать агрессию", "how_to_lead": "Направить в спорт с дисциплиной"},
                4: {"name": "Девятка — Защитник", "what_they_need": "Монетизировать силу", "how_to_lead": "Помогать переходить к профессионализму"},
                5: {"name": "Десятка — Профессионал", "what_they_need": "Перейти от времени к результату", "how_to_lead": "Направлять к предпринимательству"},
                6: {"name": "Мастер", "what_they_need": "Интеграция с другими мастями", "how_to_lead": "Развивать мудрость и влияние"}
            }
        },
        "ТФ": {
            "name": "Трудяга",
            "essence": "Выживает через создание ценности",
            "core_fear": "Бедность, ненужность, нестабильность",
            "core_need": "Стабильность и признание через результат",
            "communication": {"preference": "Структурно, алгоритмично", "message_format": "Инструкции, схемы", "what_to_avoid": "Хаос, спонтанность"},
            "levels": {
                1: {"name": "Шестёрка — Лентяй", "what_they_need": "Понять связь труда и результата", "how_to_lead": "Маленькие шаги, быстрая обратная связь"},
                2: {"name": "Семёрка — Исполнитель", "what_they_need": "Научиться выбирать", "how_to_lead": "Постепенно передавать выбор"},
                3: {"name": "Восьмёрка — Охотник за зарплатой", "what_they_need": "Понять ценность навыков", "how_to_lead": "Показывать долгосрочную выгоду"},
                4: {"name": "Девятка — Мастер-одиночка", "what_they_need": "Научиться делегировать", "how_to_lead": "Показывать выгоду от команды"},
                5: {"name": "Десятка — Организатор", "what_they_need": "Перейти к продуктам/активам", "how_to_lead": "Направлять к созданию продуктов"},
                6: {"name": "Мастер", "what_they_need": "Интеграция с ЧВ и УБ", "how_to_lead": "Развивать видение и влияние"}
            }
        },
        "УБ": {
            "name": "Умный",
            "essence": "Выживает через понимание мира",
            "core_fear": "Выглядеть глупо, ошибиться, не понять",
            "core_need": "Истина и компетентность",
            "communication": {"preference": "Логично, доказательно", "message_format": "Данные, аналитика", "what_to_avoid": "Эмоциональные аргументы"},
            "levels": {
                1: {"name": "Шестёрка — Избегающий познания", "what_they_need": "Пробудить любопытство", "how_to_lead": "Простые объяснения, связь с практикой"},
                2: {"name": "Семёрка — Магическое мышление", "what_they_need": "Научиться видеть причинно-следственные связи", "how_to_lead": "Не высмеивать, мягко показывать логику"},
                3: {"name": "Восьмёрка — Конспиролог", "what_they_need": "Научиться проверять информацию", "how_to_lead": "Предлагать проверять факты"},
                4: {"name": "Девятка — Догматик", "what_they_need": "Научиться проверять авторитетов", "how_to_lead": "Показывать, что авторитеты ошибаются"},
                5: {"name": "Десятка — Эмпирик", "what_they_need": "Научиться доверять логике", "how_to_lead": "Переводить от опыта к системам"},
                6: {"name": "Мастер", "what_they_need": "Интеграция с ЧВ и ТФ", "how_to_lead": "Развивать коммуникацию"}
            }
        },
        "ЧВ": {
            "name": "Влиятель",
            "essence": "Выживает через влияние на людей",
            "core_fear": "Одиночество, отвержение, изоляция",
            "core_need": "Признание и влияние через отношения",
            "communication": {"preference": "Тепло, эмпатично", "message_format": "Истории, метафоры", "what_to_avoid": "Холодность, игнорирование"},
            "levels": {
                1: {"name": "Шестёрка — Жертва-манипулятор", "what_they_need": "Осознать свои манипуляции", "how_to_lead": "Мягко показывать паттерн"},
                2: {"name": "Семёрка — Хамелеон", "what_they_need": "Найти себя", "how_to_lead": "Помогать исследовать свои желания"},
                3: {"name": "Восьмёрка — Мошенник", "what_they_need": "Понять, что манипуляция разрушает", "how_to_lead": "Показывать долгосрочные последствия"},
                4: {"name": "Девятка — Читатель мотивов", "what_they_need": "Перейти от использования к служению", "how_to_lead": "Перенаправлять на помощь"},
                5: {"name": "Десятка — Системный влиятель", "what_they_need": "Монетизировать влияние", "how_to_lead": "Направлять к созданию бренда"},
                6: {"name": "Мастер", "what_they_need": "Интеграция с УБ и СБ", "how_to_lead": "Развивать мудрость и защиту"}
            }
        }
    }
}


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
        if city in self.cache:
            cache_time = self.cache[city].get("cached_at", 0)
            if datetime.now().timestamp() - cache_time < 3600:  # 1 час кэша
                return self.cache[city]["data"]
        
        result = {
            "city": city,
            "weather": await self._get_weather(city),
            "timezone": await self._get_timezone(city),
            "transport": await self._get_transport_info(city),
            "safety": await self._get_safety_info(city),
            "infrastructure": await self._get_infrastructure(city),
            "events": await self._get_events(city),
            "recommendations": []
        }
        
        # Формируем рекомендации на основе данных
        result["recommendations"] = self._generate_recommendations(result)
        
        self.cache[city] = {"data": result, "cached_at": datetime.now().timestamp()}
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
        """Маппинг кодов погоды на эмодзи"""
        mapping = {
            "01d": "☀️", "01n": "🌙", "02d": "⛅", "02n": "☁️",
            "03d": "☁️", "03n": "☁️", "04d": "☁️", "04n": "☁️",
            "09d": "🌧️", "09n": "🌧️", "10d": "🌦️", "10n": "🌧️",
            "11d": "⛈️", "11n": "⛈️", "13d": "❄️", "13n": "❄️",
            "50d": "🌫️", "50n": "🌫️"
        }
        return mapping.get(icon_code, "🌡️")
    
    async def _get_timezone(self, city: str) -> Dict[str, Any]:
        """Определяет часовой пояс города"""
        # Базовая база часовых поясов для городов РФ
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
    
    async def _get_transport_info(self, city: str) -> Dict[str, Any]:
        """Информация о транспорте (заглушка, в реальности API Яндекс.Транспорт)"""
        # Базовая информация для городов-миллионников
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
    
    async def _get_safety_info(self, city: str) -> Dict[str, Any]:
        """Информация о безопасности (заглушка)"""
        return {
            "overall_rating": 7,
            "daytime_safety": 8,
            "night_safety": 6,
            "safe_districts": ["центр", "юго-запад"],
            "unsafe_districts": ["окраины"],
            "recommendations": "В тёмное время суток избегайте неосвещённых улиц"
        }
    
    async def _get_infrastructure(self, city: str) -> Dict[str, Any]:
        """Информация об инфраструктуре"""
        return {
            "hospitals": "в радиусе 3-5 км",
            "pharmacies": "в шаговой доступности",
            "schools": "в радиусе 1-2 км",
            "parks": "есть",
            "shops": "в шаговой доступности"
        }
    
    async def _get_events(self, city: str) -> List[Dict]:
        """Актуальные мероприятия (заглушка)"""
        return [
            {"name": "Выставка современного искусства", "date": "скоро", "type": "culture"},
            {"name": "Фестиваль уличной еды", "date": "выходные", "type": "food"}
        ]
    
    def _generate_recommendations(self, city_info: Dict) -> List[str]:
        """Генерирует рекомендации на основе данных о городе"""
        recommendations = []
        
        # Погодные рекомендации
        weather = city_info.get("weather", {})
        temp = weather.get("temperature")
        if temp and isinstance(temp, (int, float)):
            if temp < 0:
                recommendations.append("❄️ На улице холодно, одевайтесь теплее")
            elif temp > 25:
                recommendations.append("☀️ Жарко, не забывайте пить воду")
            elif "дождь" in weather.get("description", "").lower():
                recommendations.append("🌧️ Возьмите зонт, ожидается дождь")
        
        # Транспортные рекомендации
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
                    return {"success": True, "path": path}
                else:
                    error = await resp.text()
                    return {"success": False, "error": error}
    
    async def update_file(self, path: str, content: str, commit_message: str) -> Dict:
        """Обновляет существующий файл"""
        if not self.token:
            return {"success": False, "error": "GitHub token not configured"}
        
        # Сначала получаем SHA текущего файла
        url = f"{self.api_base}/{self.repo}/contents/{path}"
        
        async with aiohttp.ClientSession() as session:
            # Получаем текущий файл
            async with session.get(
                url,
                headers={"Authorization": f"token {self.token}"}
            ) as resp:
                if resp.status != 200:
                    return {"success": False, "error": "File not found"}
                data = await resp.json()
                sha = data.get("sha")
            
            # Обновляем файл
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
        """Генерирует шаблон Telegram бота"""
        return f'''#!/usr/bin/env python3
"""
{name} - Telegram Bot
{description}
"""

import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Токен бота (установите через переменную окружения)
TOKEN = os.environ.get("BOT_TOKEN", "YOUR_TOKEN_HERE")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    await update.message.reply_text(
        "Привет! Я {name}.\\n\\n{description}\\n\\n"
        "Используй /help для списка команд."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    await update.message.reply_text(
        "Доступные команды:\\n"
        "/start - Начать диалог\\n"
        "/help - Показать эту справку\\n"
        "/about - Информация о боте"
    )

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений"""
    text = update.message.text
    await update.message.reply_text(f"Вы сказали: {text}")

def main():
    """Запуск бота"""
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
        """Генерирует шаблон веб-приложения на FastAPI"""
        return f'''#!/usr/bin/env python3
"""
{name} - Web Application
{description}
"""

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
import uvicorn

app = FastAPI(title="{name}", description="{description}")

@app.get("/")
async def root():
    return {{
        "name": "{name}",
        "status": "running",
        "description": "{description}"
    }}

@app.get("/health")
async def health():
    return {{"status": "ok"}}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
'''
    
    def _generate_api_template(self, name: str, description: str) -> str:
        """Генерирует шаблон API"""
        return f'''#!/usr/bin/env python3
"""
{name} - API Service
{description}
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
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
    """Обработка запроса"""
    try:
        # Здесь логика обработки
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
        """Генерирует шаблон CLI приложения"""
        return f'''#!/usr/bin/env python3
"""
{name} - Command Line Tool
{description}
"""

import argparse
import sys

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
        """Отправляет запрос к DeepSeek"""
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
        """Анализирует диалог и определяет профиль пользователя"""
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
}

Никаких пояснений, только JSON."""
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(conversation[-20:], ensure_ascii=False)}
        ]
        
        response = await self.chat(messages, temperature=0.3)
        
        # Извлекаем JSON из ответа
        json_match = re.search(r'\{[^{}]*\}', response, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group())
            except:
                pass
        
        # Fallback
        return {"СБ": 3, "ТФ": 3, "УБ": 3, "ЧВ": 3, "perception_type": "СОЦИАЛЬНО-ОРИЕНТИРОВАННЫЙ", "thinking_level": 5, "dominant": "ЧВ"}
    
    async def generate_response(self, user_message: str, profile: Dict, context: Dict, conversation: List[Dict]) -> str:
        """Генерирует персонализированный ответ"""
        
        # Получаем данные о доминантной масти
        dominant = profile.get("dominant", "ЧВ")
        level = profile.get(dominant, 4)
        vector_data = VARITYPE_KB["vectors"].get(dominant, {})
        level_data = vector_data.get("levels", {}).get(level, {})
        
        system_prompt = f"""Ты Фреди, виртуальный психолог и AI-агент.

ПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ:
- Доминантная масть: {dominant} ({vector_data.get('name', '')})
- Уровень: {level} ({level_data.get('name', '')})
- Что ему нужно: {level_data.get('what_they_need', 'Помощь в развитии')}
- Как с ним общаться: {vector_data.get('communication', {}).get('preference', 'Доброжелательно')}

КОНТЕКСТ:
- Город: {context.get('city', 'не указан')}
- Погода: {context.get('weather', {}).get('description', '')}
- Время: {context.get('time', '')}

ПРАВИЛА ОБЩЕНИЯ:
1. Говори {vector_data.get('communication', {}).get('message_format', 'понятно и по делу')}
2. Избегай: {vector_data.get('communication', {}).get('what_to_avoid', 'долгих объяснений')}
3. Учитывай, что пользователю нужно: {level_data.get('what_they_need', '')}
4. Если пользователь просит не то, что ему нужно — мягко направь
5. Отвечай на русском, обращайся на «ты»

Ты можешь:
- Создавать приложения (Telegram боты, веб-приложения, API, CLI)
- Анализировать код
- Давать рекомендации по саморазвитию
- Отвечать на вопросы

Будь полезным, эмпатичным и профессиональным."""
        
        messages = [
            {"role": "system", "content": system_prompt},
            *conversation[-10:],  # последние 10 сообщений для контекста
            {"role": "user", "content": user_message}
        ]
        
        return await self.chat(messages)


# ============================================
# ГОЛОСОВОЙ СЕРВИС
# ============================================

class VoiceService:
    """Обработка голоса (STT и TTS)"""
    
    def __init__(self):
        self.yandex_key = Config.YANDEX_API_KEY
    
    async def speech_to_text(self, audio_bytes: bytes, format: str = "ogg") -> str:
        """Распознавание речи через Yandex SpeechKit"""
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
        """Синтез речи через Yandex SpeechKit"""
        if not self.yandex_key:
            return None
        
        try:
            async with aiohttp.ClientSession() as session:
                url = "https://tts.api.cloud.yandex.net/speech/v1/tts:synthesize"
                headers = {"Authorization": f"Api-Key {self.yandex_key}"}
                data = {
                    "text": text,
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
    """Состояние пользователя в диалоге"""
    
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.profile: Dict[str, Any] = {}
        self.context: Dict[str, Any] = {
            "city": None,
            "weather": None,
            "time": None,
            "conversation_started": datetime.now().isoformat()
        }
        self.conversation_history: List[Dict] = []
        self.city_info: Dict[str, Any] = {}
        self.profile_analyzed: bool = False
    
    def add_message(self, role: str, content: str):
        """Добавляет сообщение в историю"""
        self.conversation_history.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        })
        # Ограничиваем историю 50 сообщениями
        if len(self.conversation_history) > 50:
            self.conversation_history = self.conversation_history[-50:]
    
    def to_dict(self) -> Dict:
        return {
            "user_id": self.user_id,
            "profile": self.profile,
            "context": self.context,
            "profile_analyzed": self.profile_analyzed,
            "history_length": len(self.conversation_history)
        }


# ============================================
# ХРАНИЛИЩЕ СОСТОЯНИЙ
# ============================================

class StateManager:
    """Управляет состояниями пользователей"""
    
    def __init__(self):
        self._states: Dict[str, UserState] = {}
    
    def get_or_create(self, user_id: str) -> UserState:
        if user_id not in self._states:
            self._states[user_id] = UserState(user_id)
        return self._states[user_id]
    
    def save(self, user_id: str, state: UserState):
        self._states[user_id] = state
    
    def delete(self, user_id: str):
        if user_id in self._states:
            del self._states[user_id]


# ============================================
# FASTAPI ПРИЛОЖЕНИЕ
# ============================================

state_manager = StateManager()
ai_service = AIService()
voice_service = VoiceService()
city_service = CityInfoService()
github_service = GitHubService()

# Создаём HTML интерфейс
HTML_TEMPLATE = '''<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
    <title>Фреди - AI-агент</title>
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
        
        /* Шапка */
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
        
        /* Основной чат */
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
        
        /* Панель ввода */
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
        
        /* Индикатор набора */
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
        
        /* Мобильная адаптация */
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
        
        <div class="chat-container" id="chatContainer">
            <div class="message bot">
                <div class="message-bubble">
                    Привет! Я Фреди — твой виртуальный помощник.<br><br>
                    Я могу:<br>
                    • 💬 Отвечать на вопросы<br>
                    • 🎙️ Распознавать голос<br>
                    • 📝 Создавать приложения (Telegram боты, веб-приложения)<br>
                    • 🌍 Анализировать информацию о городе<br>
                    • 🧠 Помогать с саморазвитием<br><br>
                    <b>Расскажи, что тебе нужно?</b>
                    <div class="message-time">только что</div>
                </div>
            </div>
        </div>
        
        <div class="input-panel">
            <input type="text" id="messageInput" placeholder="Напишите сообщение..." autocomplete="off">
            <button class="btn btn-voice" id="voiceBtn">🎤</button>
            <button class="btn btn-send" id="sendBtn">📤</button>
        </div>
    </div>
    
    <script>
        const chatContainer = document.getElementById('chatContainer');
        const messageInput = document.getElementById('messageInput');
        const sendBtn = document.getElementById('sendBtn');
        const voiceBtn = document.getElementById('voiceBtn');
        const statusEl = document.getElementById('status');
        
        let isRecording = false;
        let mediaRecorder = null;
        let audioChunks = [];
        let userId = localStorage.getItem('fredi_user_id');
        if (!userId) {
            userId = 'user_' + Date.now();
            localStorage.setItem('fredi_user_id', userId);
        }
        
        // Добавление сообщения в чат
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
        
        // Показать индикатор набора
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
        
        // Отправка сообщения
        async function sendMessage(text, isVoice = false) {
            if (!text.trim()) return;
            
            addMessage(text, true);
            messageInput.value = '';
            showTyping();
            statusEl.textContent = '● Думаю...';
            
            try {
                const response = await fetch('/api/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
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
        
        // Голосовая запись
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
                }, 30000); // Авто-остановка через 30 секунд
                
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
        
        // Загрузка истории при старте
        async function loadHistory() {
            try {
                const response = await fetch(`/api/chat/history/${userId}`);
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
        
        loadHistory();
    </script>
</body>
</html>
'''


# ============================================
# FASTAPI ЭНДПОИНТЫ
# ============================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом приложения"""
    logger.info("🚀 Запуск Фреди AI-агента")
    yield
    logger.info("🛑 Остановка Фреди AI-агента")


app = FastAPI(
    title="Фреди AI-агент",
    description="Виртуальный помощник с возможностью создания приложений",
    version="4.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    """Главная страница"""
    return HTMLResponse(HTML_TEMPLATE)


@app.get("/health")
async def health():
    """Проверка здоровья"""
    return {
        "status": "ok",
        "services": {
            "ai": bool(Config.DEEPSEEK_API_KEY),
            "voice": bool(Config.YANDEX_API_KEY),
            "github": bool(Config.GITHUB_TOKEN),
            "weather": bool(Config.OPENWEATHER_API_KEY)
        }
    }


class ChatRequest(BaseModel):
    user_id: str
    message: str
    is_voice: bool = False


@app.post("/api/chat")
async def chat(request: ChatRequest):
    """Обработка текстового сообщения"""
    try:
        state = state_manager.get_or_create(request.user_id)
        state.add_message("user", request.message)
        
        # Если профиль ещё не проанализирован и сообщений достаточно
        if not state.profile_analyzed and len(state.conversation_history) >= 10:
            logger.info(f"Анализ профиля пользователя {request.user_id}")
            profile = await ai_service.analyze_user(state.conversation_history)
            state.profile = profile
            state.profile_analyzed = True
            state_manager.save(request.user_id, state)
        
        # Получаем город из контекста, если есть
        city = None
        for msg in state.conversation_history[-5:]:
            if msg["role"] == "user":
                # Ищем упоминание города
                city_match = re.search(r'(?:в|из|во)\s+([А-Я][а-я]+(?:-?[А-Я][а-я]+)?)(?:\s|$|,|\.)', msg["content"])
                if city_match:
                    city = city_match.group(1)
                    break
        
        if city and not state.context.get("city"):
            state.context["city"] = city
            city_info = await city_service.get_city_info(city)
            state.city_info = city_info
            state.context["weather"] = city_info.get("weather", {})
            state_manager.save(request.user_id, state)
        
        # Генерируем ответ
        response = await ai_service.generate_response(
            request.message,
            state.profile,
            state.context,
            state.conversation_history
        )
        
        # Проверяем, не хочет ли пользователь создать приложение
        if any(keyword in request.message.lower() for keyword in ["создай приложение", "сделай бота", "напиши код", "сгенерируй"]):
            # Извлекаем название и тип приложения
            app_name_match = re.search(r'(?:названием|под названием)\s+["\']?([А-Яа-яA-Za-z0-9_]+)', request.message)
            app_type = "web_app"
            if "телеграм" in request.message.lower() or "telegram" in request.message.lower() or "бот" in request.message.lower():
                app_type = "telegram_bot"
            elif "api" in request.message.lower():
                app_type = "api"
            elif "cli" in request.message.lower() or "командная строка" in request.message.lower():
                app_type = "cli"
            
            app_name = app_name_match.group(1) if app_name_match else f"app_{int(datetime.now().timestamp())}"
            
            result = await github_service.create_app(app_name, app_type, request.message[:100])
            if result.get("success"):
                response += f"\n\n✅ Приложение **{app_name}** создано!\n📁 Путь: `{result.get('path')}`\n🔗 Репозиторий: {Config.GITHUB_REPO}"
            else:
                response += f"\n\n❌ Не удалось создать приложение: {result.get('error', 'неизвестная ошибка')}"
        
        state.add_message("assistant", response)
        state_manager.save(request.user_id, state)
        
        return {"success": True, "response": response}
        
    except Exception as e:
        logger.error(f"Chat error: {e}")
        return {"success": False, "error": str(e)}


@app.post("/api/voice/process")
async def process_voice(
    user_id: str = Form(...),
    voice: UploadFile = File(...)
):
    """Обработка голосового сообщения"""
    try:
        # Читаем аудио
        audio_bytes = await voice.read()
        if len(audio_bytes) < 1000:
            return {"success": False, "error": "Аудио слишком короткое"}
        
        # Распознаём речь
        recognized_text = await voice_service.speech_to_text(audio_bytes)
        if not recognized_text:
            return {"success": False, "error": "Не удалось распознать речь"}
        
        # Обрабатываем как обычное сообщение
        state = state_manager.get_or_create(user_id)
        state.add_message("user", recognized_text)
        
        # Генерируем ответ
        response = await ai_service.generate_response(
            recognized_text,
            state.profile,
            state.context,
            state.conversation_history
        )
        
        state.add_message("assistant", response)
        
        # Синтезируем речь
        audio_response = await voice_service.text_to_speech(response[:500])  # ограничиваем длину
        
        return {
            "success": True,
            "recognized_text": recognized_text,
            "answer": response,
            "audio_base64": base64.b64encode(audio_response).decode() if audio_response else None
        }
        
    except Exception as e:
        logger.error(f"Voice processing error: {e}")
        return {"success": False, "error": str(e)}


@app.get("/api/chat/history/{user_id}")
async def get_history(user_id: str, limit: int = 50):
    """Получение истории диалога"""
    state = state_manager.get_or_create(user_id)
    history = state.conversation_history[-limit:]
    return {"success": True, "history": history}


@app.get("/api/user/profile/{user_id}")
async def get_user_profile(user_id: str):
    """Получение профиля пользователя"""
    state = state_manager.get_or_create(user_id)
    return {
        "success": True,
        "profile": state.profile,
        "context": state.context,
        "analyzed": state.profile_analyzed
    }


@app.get("/api/city/info/{city}")
async def get_city_info(city: str):
    """Получение информации о городе"""
    info = await city_service.get_city_info(city)
    return {"success": True, "info": info}


@app.post("/api/github/create-file")
async def github_create_file(
    path: str = Form(...),
    content: str = Form(...),
    message: str = Form(...)
):
    """Создание файла в GitHub"""
    result = await github_service.create_file(path, content, message)
    return result


# ============================================
# ЗАПУСК
# ============================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
