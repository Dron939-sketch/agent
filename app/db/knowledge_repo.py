"""Repository для графа знаний о пользователе.

Sprint 7: CRUD для KnowledgeFact + UserInsight, поиск, дедупликация.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .models import KnowledgeFact, UserInsight


class KnowledgeRepository:
    """Репозиторий графа знаний."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # === KnowledgeFact CRUD ===

    async def add_fact(
        self,
        user_id: str,
        subject: str,
        predicate: str,
        obj: str,
        *,
        category: str = "personal",
        confidence: float = 0.8,
        importance: int = 5,
        source: str = "auto",
    ) -> int:
        """Добавляет факт. Если дубликат — повышает confidence существующего."""
        # Проверяем дубликат
        existing = await self._find_similar_fact(user_id, subject, predicate, obj)
        if existing:
            # Повышаем confidence
            new_conf = min(1.0, existing.confidence + 0.1)
            await self.session.execute(
                update(KnowledgeFact)
                .where(KnowledgeFact.id == existing.id)
                .values(confidence=new_conf, importance=max(existing.importance, importance))
            )
            return existing.id

        fact = KnowledgeFact(
            user_id=user_id,
            subject=subject,
            predicate=predicate,
            object=obj,
            category=category,
            confidence=confidence,
            importance=importance,
            source=source,
        )
        self.session.add(fact)
        await self.session.flush()
        return fact.id

    async def _find_similar_fact(
        self,
        user_id: str,
        subject: str,
        predicate: str,
        obj: str,
    ) -> KnowledgeFact | None:
        """Ищет похожий факт (case-insensitive)."""
        result = await self.session.execute(
            select(KnowledgeFact).where(
                KnowledgeFact.user_id == user_id,
                func.lower(KnowledgeFact.subject) == subject.lower(),
                func.lower(KnowledgeFact.predicate) == predicate.lower(),
                func.lower(KnowledgeFact.object) == obj.lower(),
                KnowledgeFact.superseded_by.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_facts(
        self,
        user_id: str,
        *,
        category: str | None = None,
        subject: str | None = None,
        limit: int = 50,
        min_confidence: float = 0.3,
    ) -> list[KnowledgeFact]:
        """Получает факты пользователя с фильтрами."""
        q = (
            select(KnowledgeFact)
            .where(
                KnowledgeFact.user_id == user_id,
                KnowledgeFact.confidence >= min_confidence,
                KnowledgeFact.superseded_by.is_(None),
            )
            .order_by(KnowledgeFact.importance.desc(), KnowledgeFact.confidence.desc())
            .limit(limit)
        )
        if category:
            q = q.where(KnowledgeFact.category == category)
        if subject:
            q = q.where(func.lower(KnowledgeFact.subject) == subject.lower())

        result = await self.session.execute(q)
        return list(result.scalars().all())

    async def get_facts_about(self, user_id: str, query: str, *, limit: int = 10) -> list[KnowledgeFact]:
        """Ищет факты где query встречается в subject, predicate или object."""
        like = f"%{query.lower()}%"
        result = await self.session.execute(
            select(KnowledgeFact)
            .where(
                KnowledgeFact.user_id == user_id,
                KnowledgeFact.superseded_by.is_(None),
                (
                    func.lower(KnowledgeFact.subject).like(like)
                    | func.lower(KnowledgeFact.predicate).like(like)
                    | func.lower(KnowledgeFact.object).like(like)
                ),
            )
            .order_by(KnowledgeFact.importance.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def supersede_fact(self, old_id: int, new_id: int) -> None:
        """Помечает факт как устаревший (заменён новым)."""
        await self.session.execute(
            update(KnowledgeFact)
            .where(KnowledgeFact.id == old_id)
            .values(superseded_by=new_id)
        )

    async def count(self, user_id: str) -> int:
        result = await self.session.execute(
            select(func.count()).select_from(KnowledgeFact)
            .where(KnowledgeFact.user_id == user_id, KnowledgeFact.superseded_by.is_(None))
        )
        return int(result.scalar() or 0)

    async def get_categories_summary(self, user_id: str) -> dict[str, int]:
        """Возвращает количество фактов по категориям."""
        result = await self.session.execute(
            select(KnowledgeFact.category, func.count())
            .where(KnowledgeFact.user_id == user_id, KnowledgeFact.superseded_by.is_(None))
            .group_by(KnowledgeFact.category)
        )
        return {row[0]: row[1] for row in result.all()}

    # === UserInsight CRUD ===

    async def add_insight(
        self,
        user_id: str,
        category: str,
        insight: str,
        *,
        confidence: float = 0.6,
    ) -> int:
        """Добавляет или обновляет инсайт."""
        # Проверяем существующий инсайт той же категории
        existing = await self.session.execute(
            select(UserInsight).where(
                UserInsight.user_id == user_id,
                UserInsight.category == category,
                func.lower(UserInsight.insight) == insight.lower(),
            )
        )
        old = existing.scalar_one_or_none()
        if old:
            await self.session.execute(
                update(UserInsight)
                .where(UserInsight.id == old.id)
                .values(
                    evidence_count=old.evidence_count + 1,
                    confidence=min(1.0, old.confidence + 0.05),
                )
            )
            return old.id

        ins = UserInsight(
            user_id=user_id,
            category=category,
            insight=insight,
            confidence=confidence,
        )
        self.session.add(ins)
        await self.session.flush()
        return ins.id

    async def get_insights(
        self,
        user_id: str,
        *,
        category: str | None = None,
        limit: int = 20,
    ) -> list[UserInsight]:
        q = (
            select(UserInsight)
            .where(UserInsight.user_id == user_id)
            .order_by(UserInsight.confidence.desc(), UserInsight.evidence_count.desc())
            .limit(limit)
        )
        if category:
            q = q.where(UserInsight.category == category)
        result = await self.session.execute(q)
        return list(result.scalars().all())

    # === Форматирование для промпта ===

    async def format_knowledge_for_prompt(self, user_id: str, *, max_facts: int = 15) -> str:
        """Форматирует граф знаний для включения в system prompt."""
        facts = await self.get_facts(user_id, limit=max_facts, min_confidence=0.5)
        insights = await self.get_insights(user_id, limit=5)

        if not facts and not insights:
            return ""

        parts: list[str] = ["ГРАФ ЗНАНИЙ О ПОЛЬЗОВАТЕЛЕ:"]

        if facts:
            # Группируем по категориям
            by_cat: dict[str, list[str]] = {}
            for f in facts:
                cat = f.category
                line = f"{f.subject} {f.predicate} {f.object}"
                by_cat.setdefault(cat, []).append(line)

            cat_labels = {
                "personal": "Личное",
                "preference": "Предпочтения",
                "goal": "Цели",
                "habit": "Привычки",
                "relation": "Отношения",
                "work": "Работа",
                "health": "Здоровье",
            }

            for cat, items in by_cat.items():
                label = cat_labels.get(cat, cat.title())
                parts.append(f"  [{label}]")
                for item in items[:5]:
                    parts.append(f"  - {item}")

        if insights:
            parts.append("  [Инсайты]")
            for ins in insights:
                parts.append(f"  - {ins.insight} (уверенность: {ins.confidence:.0%})")

        parts.append("Используй эти знания для персонализированных ответов.")
        return "\n".join(parts)
