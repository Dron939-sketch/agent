"""ROUND 3 tests: Episodic memory — sessions + auto-summary + recall.

Покрывают:
- ChatSessionRepository: get_or_create_active резюмирует active сессию внутри
  окна и создаёт новую, если прошло > gap_minutes.
- stale_id возвращается для сессии без summary.
- touch инкрементирует message_count.
- summarize_dialogue: extractive fallback работает без LLM.
- summarize_session: читает сообщения из сессии и сохраняет title/summary.
- ContextAggregator подтягивает episodes и форматирует блок prompt-а.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret")

from app.db import (  # noqa: E402
    ChatSessionRepository,
    ConversationRepository,
    UserRepository,
    dispose_db,
    init_db,
    session_scope,
)
from app.services import memory as memory_pkg  # noqa: E402
from app.services.episodic import (  # noqa: E402
    _extractive_fallback,
    _parse_llm_output,
    summarize_dialogue,
    summarize_session,
)


@pytest.fixture(autouse=True)
async def _fresh_db():
    await init_db()
    memory_pkg.reset_default_memory()
    yield
    await dispose_db()
    memory_pkg.reset_default_memory()


# ======== ChatSessionRepository ========


async def test_get_or_create_active_creates_first_session() -> None:
    async with session_scope() as session:
        await UserRepository(session).create("u1", "alice", "a@x.com", "h")
        repo = ChatSessionRepository(session)
        sid, stale = await repo.get_or_create_active("u1")
        assert sid > 0
        assert stale is None
        assert await repo.count("u1") == 1


async def test_get_or_create_active_resumes_within_gap() -> None:
    async with session_scope() as session:
        await UserRepository(session).create("u1", "alice", "a@x.com", "h")
        repo = ChatSessionRepository(session)
        sid1, _ = await repo.get_or_create_active("u1")
        # Второй вызов сразу — должен резюмировать ту же сессию
        sid2, stale = await repo.get_or_create_active("u1")
        assert sid2 == sid1
        assert stale is None
        assert await repo.count("u1") == 1


async def test_get_or_create_active_opens_new_after_gap() -> None:
    async with session_scope() as session:
        await UserRepository(session).create("u1", "alice", "a@x.com", "h")
        repo = ChatSessionRepository(session)
        now = datetime.utcnow()
        sid1, _ = await repo.get_or_create_active("u1", now=now - timedelta(hours=3))

        sid2, stale = await repo.get_or_create_active("u1", now=now)
        assert sid2 != sid1
        assert stale == sid1
        assert await repo.count("u1") == 2


async def test_touch_updates_message_count_and_ended_at() -> None:
    async with session_scope() as session:
        await UserRepository(session).create("u1", "alice", "a@x.com", "h")
        repo = ChatSessionRepository(session)
        sid, _ = await repo.get_or_create_active("u1")
        await repo.touch(sid)
        await repo.touch(sid)
        await repo.touch(sid)
        cs = await repo.get(sid)
        assert cs is not None
        assert cs.message_count == 3
        assert cs.ended_at is not None


async def test_save_summary_and_list_with_summary() -> None:
    async with session_scope() as session:
        await UserRepository(session).create("u1", "alice", "a@x.com", "h")
        repo = ChatSessionRepository(session)
        sid, _ = await repo.get_or_create_active("u1")
        await repo.save_summary(sid, title="Тест", summary="Тестовый диалог")
        rows = await repo.list_with_summary("u1")
        assert len(rows) == 1
        assert rows[0].title == "Тест"
        assert rows[0].summary == "Тестовый диалог"


async def test_messages_belonging_to_session() -> None:
    async with session_scope() as session:
        await UserRepository(session).create("u1", "alice", "a@x.com", "h")
        cs_repo = ChatSessionRepository(session)
        convos = ConversationRepository(session)
        sid, _ = await cs_repo.get_or_create_active("u1")
        await convos.add("u1", "user", "привет", chat_session_id=sid)
        await convos.add("u1", "assistant", "здравствуй", chat_session_id=sid)
        await convos.add("u1", "user", "не в сессии")  # без session_id
        msgs = await cs_repo.messages(sid)
        assert len(msgs) == 2
        assert msgs[0].content == "привет"
        assert msgs[1].content == "здравствуй"


# ======== Summarizer ========


def test_extractive_fallback_empty() -> None:
    out = _extractive_fallback([])
    assert out.title
    assert out.summary


def test_extractive_fallback_real_messages() -> None:
    messages = [
        {"role": "user", "content": "расскажи про Python"},
        {"role": "assistant", "content": "Python — язык программирования."},
        {"role": "user", "content": "а про async?"},
    ]
    out = _extractive_fallback(messages)
    assert "Python" in out.title or "python" in out.title.lower()
    assert "Python" in out.summary
    assert "async" in out.summary


def test_parse_llm_output_valid_format() -> None:
    text = "TITLE: Планы на неделю\nSUMMARY: Обсудили задачи, приоритеты и дедлайны."
    out = _parse_llm_output(text, [])
    assert out.title == "Планы на неделю"
    assert out.summary.startswith("Обсудили")


def test_parse_llm_output_unstructured() -> None:
    text = "Вот что мы обсудили:\nПользователь спросил про работу и мы сделали план."
    out = _parse_llm_output(
        text,
        [{"role": "user", "content": "про работу"}],
    )
    assert out.title
    assert out.summary


async def test_summarize_dialogue_without_llm_falls_back() -> None:
    # В тестовой среде LLM-провайдеров нет, значит откатится на extractive
    messages = [
        {"role": "user", "content": "обсудим цели на год"},
        {"role": "assistant", "content": "давай — какие цели приоритетны?"},
        {"role": "user", "content": "выучить английский, пробежать марафон"},
    ]
    out = await summarize_dialogue(messages)
    assert out.title
    assert out.summary
    assert "цел" in out.summary.lower() or "английский" in out.summary.lower()


async def test_summarize_session_persists_summary() -> None:
    async with session_scope() as session:
        await UserRepository(session).create("u1", "alice", "a@x.com", "h")
        cs_repo = ChatSessionRepository(session)
        convos = ConversationRepository(session)
        sid, _ = await cs_repo.get_or_create_active("u1")
        await convos.add("u1", "user", "обсудим цели на год", chat_session_id=sid)
        await convos.add(
            "u1",
            "assistant",
            "давай — какие цели приоритетны?",
            chat_session_id=sid,
        )
        await convos.add(
            "u1",
            "user",
            "выучить английский, пробежать марафон",
            chat_session_id=sid,
        )

    out = await summarize_session(sid)
    assert out is not None
    assert out.title
    assert out.summary

    async with session_scope() as session:
        cs = await ChatSessionRepository(session).get(sid)
        assert cs is not None
        assert cs.summary == out.summary
        assert cs.title == out.title


async def test_summarize_session_skips_already_summarized() -> None:
    async with session_scope() as session:
        await UserRepository(session).create("u1", "alice", "a@x.com", "h")
        repo = ChatSessionRepository(session)
        sid, _ = await repo.get_or_create_active("u1")
        await repo.save_summary(sid, title="Уже", summary="уже есть")

    result = await summarize_session(sid)
    assert result is None


# ======== ContextAggregator episodic recall ========


async def test_context_aggregator_includes_episodes_in_prompt() -> None:
    from app.services.context import ContextAggregator
    from app.services.emotion import EmotionService

    async with session_scope() as session:
        await UserRepository(session).create("u1", "alice", "a@x.com", "h")
        repo = ChatSessionRepository(session)
        sid, _ = await repo.get_or_create_active("u1")
        await repo.save_summary(
            sid,
            title="Планы на выходные",
            summary="Обсудили поездку в горы и покупку сноуборда.",
        )

    async with session_scope() as session:
        aggregator = ContextAggregator(session, emotion_service=EmotionService())
        ctx = await aggregator.get_full_context("u1", "привет")
        assert len(ctx.episodes) >= 1
        assert any("Планы" in ep["title"] for ep in ctx.episodes)

        prompt = ContextAggregator.format_for_prompt(ctx, "ты Фреди")
        assert "ПРЕДЫДУЩИЕ ЭПИЗОДЫ" in prompt
        assert "Планы на выходные" in prompt
        assert "сноуборда" in prompt
