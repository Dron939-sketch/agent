"""Авто-извлечение структурированных фактов (тройки) из диалогов.

Sprint 7: после каждого диалога извлекаем факты в формате
(subject, predicate, object, category) и сохраняем в KnowledgeFact.
Периодически синтезируем высокоуровневые инсайты (UserInsight).
"""

from __future__ import annotations

import json
from typing import Any

from app.core.logging import get_logger
from app.db import KnowledgeRepository, session_scope
from app.services.llm import ChatMessage, LLMRouter, default_router

logger = get_logger(__name__)


EXTRACT_TRIPLES_PROMPT = """\
Извлеки ВСЕ факты о пользователе из этого диалога в формате JSON-массива.
Каждый факт — тройка (subject, predicate, object) с категорией.

Формат СТРОГО:
[
  {"subject": "пользователь", "predicate": "зовут", "object": "Андрей", "category": "personal", "importance": 8},
  {"subject": "пользователь", "predicate": "работает в", "object": "Google", "category": "work", "importance": 7}
]

Категории: personal, preference, goal, habit, relation, work, health
importance: 1-10 (10 = критически важно)

Правила:
- subject: кто/что (обычно "пользователь", или имя человека из его окружения)
- predicate: отношение/действие (глагол или предлог)
- object: значение/факт
- Извлекай ТОЛЬКО то, что пользователь ЯВНО сказал или подразумевал О СЕБЕ
- Не повторяй уже известные факты: {known_facts}
- Если ничего нового нет — верни []
"""

SYNTHESIZE_INSIGHTS_PROMPT = """\
На основе этих фактов о пользователе составь 3-5 высокоуровневых инсайтов.

Факты:
{facts}

Формат СТРОГО JSON:
[
  {"category": "personality", "insight": "Предпочитает структурированный подход к работе"},
  {"category": "communication_style", "insight": "Любит краткие ответы без воды"}
]

Категории инсайтов: routine, personality, values, communication_style, interests, goals, emotional_pattern
Только реальные выводы из фактов. Если фактов мало — верни [].
"""


def _extract_json_array(text: str) -> list[dict]:
    """Извлекает JSON массив из текста LLM-ответа."""
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return []
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return []


async def extract_knowledge_triples(
    messages: list[dict[str, str]],
    known_facts: list[str] | None = None,
    *,
    router: LLMRouter | None = None,
) -> list[dict[str, Any]]:
    """Извлекает тройки фактов из сообщений.

    Returns list of dicts: {subject, predicate, object, category, importance}
    """
    if not messages:
        return []

    llm = router or default_router()
    transcript = "\n".join(
        f"[{m.get('role', 'user')}] {m.get('content', '')}"
        for m in messages[-10:]
    )[:6000]

    known_str = ", ".join(known_facts[:10]) if known_facts else "нет"
    system = EXTRACT_TRIPLES_PROMPT.replace("{known_facts}", known_str)

    chat = [
        ChatMessage(role="system", content=system),
        ChatMessage(role="user", content=transcript),
    ]

    try:
        resp = await llm.chat(chat, profile="fast", temperature=0.1, max_tokens=800)  # type: ignore[arg-type]
        raw = _extract_json_array(resp.text)
    except Exception as exc:
        logger.warning("extract_knowledge_triples failed: %s", exc)
        return []

    valid: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        subj = str(item.get("subject", "")).strip()
        pred = str(item.get("predicate", "")).strip()
        obj = str(item.get("object", "")).strip()
        if not subj or not pred or not obj:
            continue
        valid.append({
            "subject": subj[:200],
            "predicate": pred[:200],
            "object": obj[:500],
            "category": str(item.get("category", "personal")),
            "importance": min(10, max(1, int(item.get("importance", 5)))),
        })

    return valid


async def store_knowledge_triples(
    user_id: str,
    triples: list[dict[str, Any]],
    *,
    source: str = "auto",
) -> int:
    """Сохраняет извлечённые тройки в БД."""
    if not triples:
        return 0

    stored = 0
    async with session_scope() as session:
        repo = KnowledgeRepository(session)
        for t in triples:
            try:
                await repo.add_fact(
                    user_id,
                    t["subject"],
                    t["predicate"],
                    t["object"],
                    category=t.get("category", "personal"),
                    importance=t.get("importance", 5),
                    source=source,
                )
                stored += 1
            except Exception as exc:
                logger.debug("store triple failed: %s", exc)

    return stored


async def auto_profile_after_dialogue(
    user_id: str,
    messages: list[dict[str, str]],
) -> dict[str, Any]:
    """Фоновая задача: извлекает знания после каждого диалога.

    Вызывается как background task из chat/voice endpoints.
    """
    # 1. Получаем уже известные факты для дедупликации
    known: list[str] = []
    async with session_scope() as session:
        repo = KnowledgeRepository(session)
        existing = await repo.get_facts(user_id, limit=20)
        known = [f"{f.subject} {f.predicate} {f.object}" for f in existing]

    # 2. Извлекаем новые тройки
    triples = await extract_knowledge_triples(messages, known_facts=known)

    # 3. Сохраняем
    stored = await store_knowledge_triples(user_id, triples)

    logger.info("auto_profile: user=%s extracted=%d stored=%d", user_id, len(triples), stored)
    return {"extracted": len(triples), "stored": stored}


async def synthesize_insights(user_id: str) -> int:
    """Синтезирует высокоуровневые инсайты из накопленных фактов.

    Вызывается периодически (раз в сутки) из AutonomyLoop.
    """
    async with session_scope() as session:
        repo = KnowledgeRepository(session)
        facts = await repo.get_facts(user_id, limit=30)

    if len(facts) < 5:
        return 0  # Недостаточно данных

    facts_text = "\n".join(
        f"- {f.subject} {f.predicate} {f.object} [{f.category}]"
        for f in facts
    )

    system = SYNTHESIZE_INSIGHTS_PROMPT.replace("{facts}", facts_text)
    chat = [
        ChatMessage(role="system", content=system),
        ChatMessage(role="user", content="Синтезируй инсайты."),
    ]

    try:
        llm = default_router()
        resp = await llm.chat(chat, profile="fast", temperature=0.2, max_tokens=500)  # type: ignore[arg-type]
        raw = _extract_json_array(resp.text)
    except Exception as exc:
        logger.warning("synthesize_insights failed: %s", exc)
        return 0

    stored = 0
    async with session_scope() as session:
        repo = KnowledgeRepository(session)
        for item in raw:
            if not isinstance(item, dict):
                continue
            cat = str(item.get("category", "personality"))
            ins = str(item.get("insight", "")).strip()
            if not ins:
                continue
            try:
                await repo.add_insight(user_id, cat, ins)
                stored += 1
            except Exception:
                pass

    return stored
