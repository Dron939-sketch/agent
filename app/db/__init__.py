"""Database layer.

В Фазе 1 здесь реализован async SQLAlchemy 2.0 поверх той же SQLite-схемы,
которой пользуется legacy `Database` из main.py. Это позволит постепенно
переключить вызовы без миграции данных.
"""

from .models import (
    Backup,
    Base,
    Conversation,
    Log,
    Repository,
    Session,
    Task,
    User,
)
from .repositories import (
    BackupRepository,
    ConversationRepository,
    LogRepository,
    RepoRepository,
    SessionRepository,
    TaskRepository,
    UserRepository,
)
from .session import dispose_db, get_engine, get_sessionmaker, init_db, session_scope

__all__ = [
    "Base",
    "User",
    "Session",
    "Conversation",
    "Task",
    "Log",
    "Backup",
    "Repository",
    "UserRepository",
    "SessionRepository",
    "ConversationRepository",
    "TaskRepository",
    "LogRepository",
    "BackupRepository",
    "RepoRepository",
    "get_engine",
    "get_sessionmaker",
    "session_scope",
    "init_db",
    "dispose_db",
]
