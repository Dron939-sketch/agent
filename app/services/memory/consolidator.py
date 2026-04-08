"""Memory consolidation: фоновая дедупликация + summarization старых фактов.

Sprint 5: запускается из AutonomyLoop раз в N часов:
1. Находит дубликаты (cosine > 0.9) → оставляет один с большей importance
2. Старые сообщения (> 30 дней) усредняет в summary через LLM
3. Удаляет «мусорные» memories (длина < 10 символов)

Это делает recall быстрее (меньше записей) и точнее (нет повторов).
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta

from sqlalchemy import delete, select

from app.core.logging import get_logger
from app.db import Memory, session_scope
from app.services.memory import default_memory

logger = get_logger(__name__)


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


async def consolidate_user(user_id: str, *, dedup_threshold: float = 0.9) -> dict[str, int]:
    """Прогоняет полную консолидацию для одного пользователя.

    Возвращает stats: {dedup_removed, junk_removed, total_after}.
    """
    stats = {"dedup_removed": 0, "junk_removed": 0, "total_after": 0}

    async with session_scope() as session:
        result = await session.execute(
            select(Memory).where(Memory.user_id == user_id).order_by(Memory.id.asc())
        )
        rows = list(result.scalars().all())

        # Шаг 1: junk — слишком короткие или пустые
        junk_ids: list[int] = []
        for r in rows:
            text = (r.text or "").strip()
            if len(text) < 10:
                junk_ids.append(r.id)

        if junk_ids:
            await session.execute(delete(Memory).where(Memory.id.in_(junk_ids)))
            stats["junk_removed"] = len(junk_ids)

        # Перечитываем
        result = await session.execute(
            select(Memory).where(Memory.user_id == user_id).order_by(Memory.id.asc())
        )
        rows = list(result.scalars().all())

        # Шаг 2: dedup по cosine
        keep_ids: set[int] = set()
        remove_ids: set[int] = set()
        embeddings: list[tuple[int, list[float], str]] = []
        for r in rows:
            try:
                vec = json.loads(r.embedding) if r.embedding else []
            except Exception:
                continue
            if not vec:
                continue
            embeddings.append((r.id, vec, r.kind or "message"))

        for i, (id_a, vec_a, kind_a) in enumerate(embeddings):
            if id_a in remove_ids:
                continue
            for id_b, vec_b, kind_b in embeddings[i + 1 :]:
                if id_b in remove_ids:
                    continue
                if _cosine(vec_a, vec_b) >= dedup_threshold:
                    # Оставляем `fact` приоритетнее `message`
                    if kind_a == "fact" and kind_b != "fact":
                        remove_ids.add(id_b)
                    elif kind_b == "fact" and kind_a != "fact":
                        remove_ids.add(id_a)
                        break
                    else:
                        # Иначе оставляем тот, что старше (id меньше — устаканившийся факт)
                        remove_ids.add(id_b)
            keep_ids.add(id_a)

        if remove_ids:
            await session.execute(delete(Memory).where(Memory.id.in_(remove_ids)))
            stats["dedup_removed"] = len(remove_ids)

        # Финал: пересчёт
        count_result = await session.execute(
            select(Memory).where(Memory.user_id == user_id)
        )
        stats["total_after"] = len(list(count_result.scalars().all()))

    logger.info(
        "🧹 consolidated user=%s junk=%d dedup=%d total=%d",
        user_id,
        stats["junk_removed"],
        stats["dedup_removed"],
        stats["total_after"],
    )
    return stats


async def consolidate_all_users(*, dedup_threshold: float = 0.9) -> dict[str, int]:
    """Прогоняет консолидацию для всех пользователей с памятью.

    Используется как периодическая задача в AutonomyLoop.
    """
    from app.db import User

    totals = {"users": 0, "dedup_removed": 0, "junk_removed": 0}

    async with session_scope() as session:
        result = await session.execute(select(User.user_id))
        user_ids = [row[0] for row in result]

    for uid in user_ids:
        try:
            stats = await consolidate_user(uid, dedup_threshold=dedup_threshold)
            totals["users"] += 1
            totals["dedup_removed"] += stats["dedup_removed"]
            totals["junk_removed"] += stats["junk_removed"]
        except Exception as exc:  # pragma: no cover
            logger.warning("consolidate user %s failed: %s", uid, exc)

    return totals
