"""Sprint 7 tests: KnowledgeRepository, fact dedup, insight storage."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret")

from app.db import KnowledgeRepository, dispose_db, init_db, session_scope  # noqa: E402


@pytest.fixture(autouse=True)
async def setup_db():
    await init_db()
    yield
    await dispose_db()


# ======== KnowledgeFact CRUD ========


@pytest.mark.asyncio
async def test_add_and_get_fact() -> None:
    async with session_scope() as session:
        repo = KnowledgeRepository(session)
        fact_id = await repo.add_fact(
            "user1", "пользователь", "зовут", "Андрей",
            category="personal", importance=9,
        )
        assert fact_id > 0

        facts = await repo.get_facts("user1")
        assert len(facts) == 1
        assert facts[0].subject == "пользователь"
        assert facts[0].predicate == "зовут"
        assert facts[0].object == "Андрей"
        assert facts[0].category == "personal"
        assert facts[0].importance == 9


@pytest.mark.asyncio
async def test_fact_dedup_raises_confidence() -> None:
    async with session_scope() as session:
        repo = KnowledgeRepository(session)
        id1 = await repo.add_fact("user1", "пользователь", "любит", "кофе", confidence=0.7)
        id2 = await repo.add_fact("user1", "пользователь", "любит", "кофе", confidence=0.7)

        # Same fact → same ID, confidence increased
        assert id1 == id2

        facts = await repo.get_facts("user1")
        assert len(facts) == 1
        assert facts[0].confidence >= 0.79  # 0.7 + 0.1 (float rounding)


@pytest.mark.asyncio
async def test_multiple_different_facts() -> None:
    """Different facts are stored separately."""
    async with session_scope() as session:
        repo = KnowledgeRepository(session)
        await repo.add_fact("user_ci", "пользователь", "любит", "кофе")
        await repo.add_fact("user_ci", "пользователь", "любит", "чай")
        facts = await repo.get_facts("user_ci")
        assert len(facts) == 2


@pytest.mark.asyncio
async def test_get_facts_by_category() -> None:
    async with session_scope() as session:
        repo = KnowledgeRepository(session)
        await repo.add_fact("user1", "пользователь", "работает в", "Google", category="work")
        await repo.add_fact("user1", "пользователь", "любит", "пиццу", category="preference")

        work_facts = await repo.get_facts("user1", category="work")
        assert len(work_facts) == 1
        assert work_facts[0].object == "Google"

        pref_facts = await repo.get_facts("user1", category="preference")
        assert len(pref_facts) == 1
        assert pref_facts[0].object == "пиццу"


@pytest.mark.asyncio
async def test_get_facts_about_search() -> None:
    async with session_scope() as session:
        repo = KnowledgeRepository(session)
        await repo.add_fact("user1", "пользователь", "работает в", "Google", category="work")
        await repo.add_fact("user1", "пользователь", "любит", "Python", category="preference")

        results = await repo.get_facts_about("user1", "google")
        assert len(results) == 1
        assert results[0].object == "Google"

        results = await repo.get_facts_about("user1", "python")
        assert len(results) == 1


@pytest.mark.asyncio
async def test_supersede_fact() -> None:
    async with session_scope() as session:
        repo = KnowledgeRepository(session)
        old_id = await repo.add_fact("user1", "пользователь", "живёт в", "Москве")
        new_id = await repo.add_fact("user1", "пользователь", "живёт в", "Питере")
        await repo.supersede_fact(old_id, new_id)

        facts = await repo.get_facts("user1")
        # Only the non-superseded fact should show
        assert len(facts) == 1
        assert facts[0].object == "Питере"


@pytest.mark.asyncio
async def test_count_facts() -> None:
    async with session_scope() as session:
        repo = KnowledgeRepository(session)
        assert await repo.count("user1") == 0
        await repo.add_fact("user1", "s", "p", "o1")
        await repo.add_fact("user1", "s", "p", "o2")
        assert await repo.count("user1") == 2


@pytest.mark.asyncio
async def test_categories_summary() -> None:
    async with session_scope() as session:
        repo = KnowledgeRepository(session)
        await repo.add_fact("user1", "s", "p", "o1", category="work")
        await repo.add_fact("user1", "s", "p", "o2", category="work")
        await repo.add_fact("user1", "s", "p", "o3", category="personal")

        summary = await repo.get_categories_summary("user1")
        assert summary["work"] == 2
        assert summary["personal"] == 1


# ======== UserInsight ========


@pytest.mark.asyncio
async def test_add_and_get_insight() -> None:
    async with session_scope() as session:
        repo = KnowledgeRepository(session)
        ins_id = await repo.add_insight("user1", "personality", "Предпочитает краткие ответы")
        assert ins_id > 0

        insights = await repo.get_insights("user1")
        assert len(insights) == 1
        assert insights[0].insight == "Предпочитает краткие ответы"


@pytest.mark.asyncio
async def test_multiple_insights_different() -> None:
    """Different insights are stored separately."""
    async with session_scope() as session:
        repo = KnowledgeRepository(session)
        await repo.add_insight("user_ins", "personality", "Любит структуру")
        await repo.add_insight("user_ins", "communication_style", "Предпочитает краткость")
        insights = await repo.get_insights("user_ins")
        assert len(insights) == 2


# ======== Format for prompt ========


@pytest.mark.asyncio
async def test_format_knowledge_empty() -> None:
    async with session_scope() as session:
        repo = KnowledgeRepository(session)
        prompt = await repo.format_knowledge_for_prompt("user_empty")
        assert prompt == ""


@pytest.mark.asyncio
async def test_format_knowledge_with_facts() -> None:
    async with session_scope() as session:
        repo = KnowledgeRepository(session)
        await repo.add_fact("user1", "пользователь", "зовут", "Андрей", category="personal", importance=9, confidence=0.9)
        await repo.add_fact("user1", "пользователь", "любит", "Python", category="preference", importance=8, confidence=0.8)

        prompt = await repo.format_knowledge_for_prompt("user1")
        assert "ГРАФ ЗНАНИЙ О ПОЛЬЗОВАТЕЛЕ:" in prompt
        assert "Андрей" in prompt
        assert "Python" in prompt
