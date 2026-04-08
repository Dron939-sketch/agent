"""ChatSessionRepository — эпизодические сессии диалогов (ROUND 3).

Идея: вместо плоской истории диалога группируем сообщения в «сессии».
Когда пользователь молчит > SESSION_GAP_MINUTES, следующая реплика
начинает новую сессию. Каждую закрытую сессию мы суммаризуем через LLM,
и эти краткие сводки подтягиваются в будущие промпты как эпизодическая
память.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .models import ChatSession, Conversation

SESSION_GAP_MINUTES = 60  # порог неактивности для новой сессии


class ChatSessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_or_create_active(
        self,
        user_id: str,
        *,
        now: datetime | None = None,
        gap_minutes: int = SESSION_GAP_MINUTES,
    ) -> tuple[int, int | None]:
        """Возвращает (active_session_id, stale_session_id).

        Если последняя сессия активна и с момента её ended_at/started_at
        прошло меньше ``gap_minutes`` — возвращаем её id.
        Иначе создаём новую; если предыдущая была «подвешена» (не закрыта),
        возвращаем её id как stale — вызывающий код может запустить
        автосуммаризацию.
        """
        now = now or datetime.utcnow()

        result = await self.session.execute(
            select(ChatSession)
            .where(ChatSession.user_id == user_id)
            .order_by(ChatSession.id.desc())
            .limit(1)
        )
        last = result.scalars().first()

        if last is not None:
            last_activity = last.ended_at or last.started_at
            gap = now - last_activity
            if gap < timedelta(minutes=gap_minutes) and last.summary is None:
                # продолжаем текущую сессию
                return last.id, None

        # Создаём новую сессию; если last существует и ещё без summary —
        # помечаем её как stale, чтобы код выше засуммаризовал.
        stale_id: int | None = None
        if last is not None and last.summary is None:
            stale_id = last.id
            # помечаем «закрыто» моментом, когда пришло новое сообщение —
            # так ended_at отражает реальный конец активности
            await self.session.execute(
                update(ChatSession)
                .where(ChatSession.id == last.id)
                .values(ended_at=now)
            )

        new_session = ChatSession(
            user_id=user_id,
            started_at=now,
            ended_at=now,
            message_count=0,
        )
        self.session.add(new_session)
        await self.session.flush()
        return new_session.id, stale_id

    async def touch(self, session_id: int, *, now: datetime | None = None) -> None:
        """Обновляет ended_at + инкрементирует message_count."""
        now = now or datetime.utcnow()
        await self.session.execute(
            update(ChatSession)
            .where(ChatSession.id == session_id)
            .values(
                ended_at=now,
                message_count=ChatSession.message_count + 1,
            )
        )

    async def get(self, session_id: int) -> Optional[ChatSession]:
        return await self.session.get(ChatSession, session_id)

    async def save_summary(
        self, session_id: int, *, title: str | None, summary: str
    ) -> None:
        await self.session.execute(
            update(ChatSession)
            .where(ChatSession.id == session_id)
            .values(title=title, summary=summary)
        )

    async def list_with_summary(
        self, user_id: str, *, limit: int = 5
    ) -> list[ChatSession]:
        """Недавние сессии, у которых уже есть summary (для episodic recall)."""
        result = await self.session.execute(
            select(ChatSession)
            .where(
                ChatSession.user_id == user_id,
                ChatSession.summary.is_not(None),
            )
            .order_by(ChatSession.id.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def messages(self, session_id: int, limit: int = 200) -> list[Conversation]:
        """Все сообщения, принадлежащие сессии (в хронологическом порядке)."""
        result = await self.session.execute(
            select(Conversation)
            .where(Conversation.chat_session_id == session_id)
            .order_by(Conversation.id.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def count(self, user_id: str) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(ChatSession)
            .where(ChatSession.user_id == user_id)
        )
        return int(result.scalar() or 0)
