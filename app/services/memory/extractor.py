"""Авто-извлечение фактов о пользователе из истории диалога через LLMRouter."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from app.core.logging import get_logger
from app.services.llm import ChatMessage, LLMRouter

logger = get_logger(__name__)


@dataclass(slots=True)
class ExtractedFact:
    fact: str
    type: str  # personal | goal | fear | achievement | preference | value
    importance: int

    def to_dict(self) -> dict[str, Any]:
        return {"fact": self.fact, "type": self.type, "importance": self.importance}


SYSTEM_PROMPT = (
    "Извлеки ВАЖНЫЕ факты о пользователе из диалога. "
    "Верни СТРОГО JSON массив без обёрток:\n"
    '[{"fact": "...", "type": "personal|goal|fear|achievement|preference|value", '
    '"importance": 1-10}]\n'
    "Только то, что пользователь явно сказал О СЕБЕ. Без интерпретаций. "
    "Если ничего важного нет — верни []."
)


def _extract_json_array(text: str) -> str:
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return "[]"
    return text[start : end + 1]


async def extract_facts(
    router: LLMRouter,
    messages: list[dict[str, str]],
    *,
    profile: str = "fast",
) -> list[ExtractedFact]:
    """Прогоняет последние сообщения через LLM и достаёт список фактов."""
    if not messages:
        return []

    transcript = "\n".join(
        f"[{m.get('role', 'user')}] {m.get('content', '')}" for m in messages[-10:]
    )

    chat = [
        ChatMessage(role="system", content=SYSTEM_PROMPT),
        ChatMessage(role="user", content=transcript[:8000]),
    ]
    try:
        resp = await router.chat(chat, profile=profile, temperature=0.1, max_tokens=600)  # type: ignore[arg-type]
        raw = json.loads(_extract_json_array(resp.text))
    except Exception as exc:
        logger.warning("extract_facts failed: %s", exc)
        return []

    out: list[ExtractedFact] = []
    for item in raw:
        try:
            out.append(
                ExtractedFact(
                    fact=str(item["fact"])[:500],
                    type=str(item.get("type", "personal")),
                    importance=int(item.get("importance", 5)),
                )
            )
        except Exception:
            continue
    return out
