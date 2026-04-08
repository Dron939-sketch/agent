"""SQLAlchemy 2.0 декларативные модели Фреди.

Все таблицы с префиксом `fr_*`.
ROUND 1: + Goal, HabitCheck, ChatSession.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Базовый класс для всех моделей."""


class User(Base):
    __tablename__ = "fr_users"

    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    username: Mapped[Optional[str]] = mapped_column(String, unique=True, index=True)
    email: Mapped[Optional[str]] = mapped_column(String, unique=True, index=True)
    password_hash: Mapped[Optional[str]] = mapped_column(String)
    profile: Mapped[Optional[str]] = mapped_column(Text)
    context: Mapped[Optional[str]] = mapped_column(Text)
    settings: Mapped[Optional[str]] = mapped_column(Text)
    is_active: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.current_timestamp(), onupdate=func.current_timestamp()
    )

    sessions: Mapped[list["Session"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    messages: Mapped[list["Conversation"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Session(Base):
    __tablename__ = "fr_sessions"

    token: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("fr_users.user_id"), index=True)
    expires_at: Mapped[datetime]
    created_at: Mapped[datetime] = mapped_column(server_default=func.current_timestamp())

    user: Mapped[User] = relationship(back_populates="sessions")


class Conversation(Base):
    __tablename__ = "fr_conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("fr_users.user_id"), index=True)
    role: Mapped[str] = mapped_column(String)
    content: Mapped[str] = mapped_column(Text)
    extra_metadata: Mapped[Optional[str]] = mapped_column("metadata", Text)
    chat_session_id: Mapped[Optional[int]] = mapped_column(Integer, index=True)
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.current_timestamp(), index=True
    )

    user: Mapped[User] = relationship(back_populates="messages")


class Task(Base):
    __tablename__ = "fr_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[str]] = mapped_column(String, index=True)
    task_type: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="pending", index=True)
    data: Mapped[Optional[str]] = mapped_column(Text)
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(index=True)
    executed_at: Mapped[Optional[datetime]]
    result: Mapped[Optional[str]] = mapped_column(Text)
    error: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.current_timestamp())


class Log(Base):
    __tablename__ = "fr_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    level: Mapped[str] = mapped_column(String)
    message: Mapped[str] = mapped_column(Text)
    extra_metadata: Mapped[Optional[str]] = mapped_column("metadata", Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.current_timestamp())


class Backup(Base):
    __tablename__ = "fr_backups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    backup_path: Mapped[str] = mapped_column(String)
    size: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(server_default=func.current_timestamp())


class Repository(Base):
    __tablename__ = "fr_repositories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String, index=True)
    repo_name: Mapped[str] = mapped_column(String)
    repo_url: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(server_default=func.current_timestamp())


class Memory(Base):
    """Персистентная векторная память."""

    __tablename__ = "fr_memories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String, index=True)
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String, default="message")
    extra_metadata: Mapped[Optional[str]] = mapped_column("metadata", Text)
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.current_timestamp(), index=True
    )


class PushSubscription(Base):
    __tablename__ = "fr_push_subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String, index=True)
    endpoint: Mapped[str] = mapped_column(Text, index=True)
    payload: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.current_timestamp())


class EmotionEvent(Base):
    __tablename__ = "fr_emotion_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String, index=True)
    primary: Mapped[str] = mapped_column(String)
    intensity: Mapped[int] = mapped_column(Integer, default=5)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    tone: Mapped[Optional[str]] = mapped_column(String)
    needs_support: Mapped[int] = mapped_column(Integer, default=0)
    source: Mapped[str] = mapped_column(String, default="text")
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.current_timestamp(), index=True
    )


class Feedback(Base):
    __tablename__ = "fr_feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String, index=True)
    message_id: Mapped[Optional[int]] = mapped_column(Integer, index=True)
    score: Mapped[int] = mapped_column(Integer)
    note: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.current_timestamp(), index=True
    )


# ============== ROUND 1: Life-coach features ==============


class Goal(Base):
    """Цель пользователя — то, к чему он движется."""

    __tablename__ = "fr_goals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String, index=True)
    title: Mapped[str] = mapped_column(String)
    description: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String, default="active", index=True)  # active/done/paused/dropped
    target_date: Mapped[Optional[datetime]]
    progress_pct: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.current_timestamp(), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.current_timestamp(), onupdate=func.current_timestamp()
    )


class Habit(Base):
    """Привычка пользователя — повторяющееся действие."""

    __tablename__ = "fr_habits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String, index=True)
    title: Mapped[str] = mapped_column(String)
    cadence: Mapped[str] = mapped_column(String, default="daily")  # daily/weekly/custom
    streak: Mapped[int] = mapped_column(Integer, default=0)
    longest_streak: Mapped[int] = mapped_column(Integer, default=0)
    last_check_at: Mapped[Optional[datetime]] = mapped_column(index=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.current_timestamp())


class HabitCheck(Base):
    """Отметка выполнения привычки за день."""

    __tablename__ = "fr_habit_checks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    habit_id: Mapped[int] = mapped_column(ForeignKey("fr_habits.id"), index=True)
    user_id: Mapped[str] = mapped_column(String, index=True)
    note: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.current_timestamp(), index=True
    )


class ChatSession(Base):
    """Эпизодическая сессия чата (для ROUND 3)."""

    __tablename__ = "fr_chat_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String, index=True)
    title: Mapped[Optional[str]] = mapped_column(String)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(
        server_default=func.current_timestamp(), index=True
    )
    ended_at: Mapped[Optional[datetime]]
    message_count: Mapped[int] = mapped_column(Integer, default=0)
