"""Авто-суммаризация диалога через LLMRouter."""

from __future__ import annotations

from app.services.llm import ChatMessage, LLMRouter

SYSTEM_PROMPT = (
    "Ты — компрессор контекста. Получив диалог пользователя и ассистента, "
    "выдай краткую сводку (5-10 предложений), сохраняющую факты, цели "
    "пользователя, неоконченные задачи и важные предпочтения. "
    "Не добавляй ничего от себя, не комментируй формат."
)


async def summarize_messages(
    router: LLMRouter,
    messages: list[dict[str, str]],
    *,
    profile: str = "fast",
) -> str:
    """Принимает обычные диалоговые сообщения и возвращает текстовую сводку."""
    if not messages:
        return ""

    transcript_lines = []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        transcript_lines.append(f"[{role}] {content}")
    transcript = "\n".join(transcript_lines)

    chat = [
        ChatMessage(role="system", content=SYSTEM_PROMPT),
        ChatMessage(role="user", content=transcript[:12000]),
    ]
    response = await router.chat(chat, profile=profile, temperature=0.2)  # type: ignore[arg-type]
    return response.text.strip()
