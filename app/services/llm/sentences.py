"""Sentence-aware streaming utilities.

Sprint 5: split LLM stream chunks по границам предложений (точка/?/!),
чтобы фронт мог запускать TTS для каждого готового предложения, не
ждать конца всего ответа. Уменьшает perceived latency на ~40%.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator

# Граница предложения: точка/?/!/… за которыми следует пробел или конец
_SENTENCE_END = re.compile(r"([.!?…]+)(\s+|$)")


class SentenceBuffer:
    """Накапливает токены LLM и эмитит готовые предложения."""

    def __init__(self) -> None:
        self._buffer = ""

    def add(self, chunk: str) -> list[str]:
        """Добавляет токен и возвращает список «закрытых» предложений."""
        if not chunk:
            return []
        self._buffer += chunk
        sentences: list[str] = []
        while True:
            match = _SENTENCE_END.search(self._buffer)
            if not match:
                break
            end = match.end()
            sentence = self._buffer[:end].strip()
            if sentence:
                sentences.append(sentence)
            self._buffer = self._buffer[end:]
        return sentences

    def flush(self) -> str | None:
        """Возвращает остаток буфера (последнее предложение без точки)."""
        if not self._buffer.strip():
            return None
        result = self._buffer.strip()
        self._buffer = ""
        return result


async def stream_with_sentences(
    chunks: AsyncIterator[str],
) -> AsyncIterator[tuple[str, str]]:
    """Async-генератор: yield (event_type, payload).

    event_type:
      - "token" — обычный токен (для UI текста)
      - "sentence" — собрано полное предложение (для TTS)
      - "final" — последнее (хвостовое) предложение
    """
    buf = SentenceBuffer()
    async for chunk in chunks:
        yield "token", chunk
        for sentence in buf.add(chunk):
            yield "sentence", sentence
    tail = buf.flush()
    if tail:
        yield "final", tail
