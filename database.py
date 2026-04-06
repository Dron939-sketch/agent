# database.py
import sqlite3
import json
from datetime import datetime
from typing import Dict, Any, List, Optional
from pathlib import Path

class Database:
    def __init__(self, db_path: str = "assistant.db"):
        self.db_path = db_path
        self._init_tables()
    
    def _init_tables(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    username TEXT,
                    email TEXT,
                    profile JSONB,
                    context JSONB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT,
                    role TEXT,
                    content TEXT,
                    metadata JSONB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT,
                    task_type TEXT,
                    status TEXT DEFAULT 'pending',
                    data JSONB,
                    scheduled_at TIMESTAMP,
                    executed_at TIMESTAMP,
                    result JSONB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    level TEXT,
                    message TEXT,
                    metadata JSONB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS backups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    backup_path TEXT,
                    size INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
    
    def save_user(self, user_id: str, data: Dict):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO users (user_id, profile, context, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """, (user_id, json.dumps(data.get("profile", {})), json.dumps(data.get("context", {}))))
    
    def get_user(self, user_id: str) -> Optional[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute("SELECT profile, context FROM users WHERE user_id = ?", (user_id,))
            row = cur.fetchone()
            if row:
                return {
                    "profile": json.loads(row[0]) if row[0] else {},
                    "context": json.loads(row[1]) if row[1] else {}
                }
        return None
    
    def add_message(self, user_id: str, role: str, content: str, metadata: Dict = None):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO conversations (user_id, role, content, metadata) VALUES (?, ?, ?, ?)",
                (user_id, role, content, json.dumps(metadata or {}))
            )
    
    def get_history(self, user_id: str, limit: int = 50) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                "SELECT role, content, created_at FROM conversations WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
                (user_id, limit)
            )
            return [{"role": row[0], "content": row[1], "timestamp": row[2]} for row in cur.fetchall()][::-1]
    
    def add_task(self, user_id: str, task_type: str, data: Dict, scheduled_at: datetime = None):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO tasks (user_id, task_type, data, scheduled_at) VALUES (?, ?, ?, ?)",
                (user_id, task_type, json.dumps(data), scheduled_at)
            )
    
    def get_pending_tasks(self) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                "SELECT id, user_id, task_type, data, scheduled_at FROM tasks WHERE status = 'pending' AND (scheduled_at IS NULL OR scheduled_at <= CURRENT_TIMESTAMP)"
            )
            return [{"id": row[0], "user_id": row[1], "task_type": row[2], "data": json.loads(row[3]), "scheduled_at": row[4]} for row in cur.fetchall()]
    
    def update_task_status(self, task_id: int, status: str, result: Dict = None):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE tasks SET status = ?, executed_at = CURRENT_TIMESTAMP, result = ? WHERE id = ?",
                (status, json.dumps(result or {}), task_id)
            )
    
    def add_log(self, level: str, message: str, metadata: Dict = None):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO logs (level, message, metadata) VALUES (?, ?, ?)",
                (level, message, json.dumps(metadata or {}))
            )
    
    def backup(self) -> str:
        """Создаёт резервную копию базы данных"""
        backup_path = f"backups/assistant_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        Path("backups").mkdir(exist_ok=True)
        
        with sqlite3.connect(self.db_path) as src, sqlite3.connect(backup_path) as dst:
            src.backup(dst)
        
        size = Path(backup_path).stat().st_size
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("INSERT INTO backups (backup_path, size) VALUES (?, ?)", (backup_path, size))
        
        return backup_path
