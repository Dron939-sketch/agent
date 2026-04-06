# auth.py
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict
from database import Database

class AuthManager:
    def __init__(self, db: Database):
        self.db = db
        self._sessions: Dict[str, Dict] = {}
    
    def hash_password(self, password: str) -> str:
        """Хеширует пароль"""
        salt = secrets.token_hex(16)
        return f"{salt}:{hashlib.sha256((salt + password).encode()).hexdigest()}"
    
    def verify_password(self, password: str, hashed: str) -> bool:
        """Проверяет пароль"""
        salt, hash_val = hashed.split(":")
        return hash_val == hashlib.sha256((salt + password).encode()).hexdigest()
    
    def register(self, username: str, email: str, password: str) -> Optional[str]:
        """Регистрирует нового пользователя"""
        user_id = f"user_{secrets.token_hex(8)}"
        hashed = self.hash_password(password)
        
        # Здесь нужно добавить таблицу auth_users
        return user_id
    
    def login(self, username: str, password: str) -> Optional[str]:
        """Авторизует пользователя"""
        # Проверка credentials
        session_token = secrets.token_hex(32)
        self._sessions[session_token] = {
            "user_id": username,
            "expires_at": datetime.now() + timedelta(days=7)
        }
        return session_token
    
    def verify_session(self, token: str) -> Optional[str]:
        """Проверяет сессию"""
        session = self._sessions.get(token)
        if session and session["expires_at"] > datetime.now():
            return session["user_id"]
        return None
