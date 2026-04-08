"""Dashboard endpoints: mood graph, stats, conversation export."""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthenticatedUser
from app.db import ConversationRepository, EmotionEvent, FeedbackRepository, MemoryRepository
from app.services.memory import default_memory

from .deps import get_current_user, get_session

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


class MoodPoint(BaseModel):
    timestamp: str
    primary: str
    intensity: int
    confidence: float
    tone: str | None = None


class MoodGraphResponse(BaseModel):
    days: int
    points: list[MoodPoint]
    distribution: dict[str, int]
    dominant: str | None
    avg_intensity: float


class StatsResponse(BaseModel):
    messages_total: int
    memories_count: int
    feedback_likes: int
    feedback_dislikes: int
    cache_hit_rate_pct: float
    voice: str | None = None


@router.get("/mood", response_model=MoodGraphResponse)
async def mood_graph(
    days: int = Query(default=7, ge=1, le=30),
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MoodGraphResponse:
    """Эмоциональная история за N дней."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    result = await session.execute(
        select(EmotionEvent)
        .where(EmotionEvent.user_id == user.user_id, EmotionEvent.created_at >= cutoff)
        .order_by(EmotionEvent.id.asc())
    )
    rows = list(result.scalars().all())

    points = [
        MoodPoint(
            timestamp=r.created_at.isoformat() if r.created_at else "",
            primary=r.primary,
            intensity=r.intensity or 5,
            confidence=r.confidence or 0.0,
            tone=r.tone,
        )
        for r in rows
    ]

    distribution: dict[str, int] = {}
    for p in points:
        distribution[p.primary] = distribution.get(p.primary, 0) + 1

    dominant = max(distribution, key=distribution.get) if distribution else None
    avg_intensity = (
        round(sum(p.intensity for p in points) / len(points), 2) if points else 0.0
    )

    return MoodGraphResponse(
        days=days,
        points=points,
        distribution=distribution,
        dominant=dominant,
        avg_intensity=avg_intensity,
    )


@router.get("/stats", response_model=StatsResponse)
async def stats(
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> StatsResponse:
    """Сводка по аккаунту: сообщения, память, лайки, cache rate."""
    history = await ConversationRepository(session).history(user.user_id, limit=10000)
    memories = await MemoryRepository(session).count_for_user(user.user_id)
    fb_stats = await FeedbackRepository(session).stats(user.user_id)

    cache_stats = default_memory().cache_stats()
    hit_rate = float(cache_stats.get("hit_rate_pct", 0.0))

    return StatsResponse(
        messages_total=len(history),
        memories_count=memories,
        feedback_likes=fb_stats.get("likes", 0),
        feedback_dislikes=fb_stats.get("dislikes", 0),
        cache_hit_rate_pct=hit_rate,
    )


@router.get("/export", response_class=PlainTextResponse)
async def export_conversation(
    format: str = Query(default="markdown", pattern="^(markdown|json)$"),
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> str:
    """Экспорт всей истории диалога. format: markdown | json."""
    rows = await ConversationRepository(session).history(user.user_id, limit=10000)
    if format == "json":
        import json

        return json.dumps(
            [
                {
                    "id": r.get("id"),
                    "role": r["role"],
                    "content": r["content"],
                    "timestamp": str(r.get("timestamp", "")),
                }
                for r in rows
            ],
            ensure_ascii=False,
            indent=2,
        )

    # Markdown
    lines = [f"# История диалога с Фреди\n", f"Пользователь: @{user.username}\n"]
    for r in rows:
        ts = r.get("timestamp", "")
        prefix = "**Ты**" if r["role"] == "user" else "**Фреди**"
        lines.append(f"\n### {prefix} · {ts}\n\n{r['content']}\n")
    return "\n".join(lines)
