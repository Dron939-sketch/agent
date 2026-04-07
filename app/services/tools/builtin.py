"""Встроенные tools: время, калькулятор, fetch URL, web search."""

from __future__ import annotations

import ast
import operator
from datetime import datetime, timezone

import aiohttp

from .registry import tool

# ---------- безопасный калькулятор ----------

_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
    ast.FloorDiv: operator.floordiv,
}


def _eval(node: ast.AST) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, int | float):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.left), _eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.operand))
    raise ValueError(f"unsupported expression: {ast.dump(node)}")


@tool(name="calculator", description="Вычисляет арифметическое выражение (+,-,*,/,%,**, унарные).")
async def calculator(expression: str) -> str:
    """Возвращает результат вычисления выражения как строку."""
    try:
        tree = ast.parse(expression, mode="eval")
        result = _eval(tree.body)
        return str(result)
    except Exception as exc:
        return f"error: {exc}"


@tool(name="now", description="Возвращает текущие дату и время в ISO-8601 (UTC).")
async def now() -> str:
    return datetime.now(timezone.utc).isoformat()


@tool(name="fetch_url", description="Скачивает содержимое URL и возвращает первые 4000 символов.")
async def fetch_url(url: str) -> str:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=15) as resp:
                if resp.status != 200:
                    return f"http error {resp.status}"
                text = await resp.text()
                return text[:4000]
    except Exception as exc:
        return f"error: {exc}"


@tool(name="web_search", description="Поиск в DuckDuckGo, возвращает топ-результаты текстом.")
async def web_search(query: str, max_results: int = 5) -> str:
    try:
        from duckduckgo_search import DDGS

        with DDGS() as ddgs:
            hits = list(ddgs.text(query, max_results=max_results))
        if not hits:
            return "(no results)"
        return "\n\n".join(
            f"- {h.get('title', '')}\n  {h.get('href', '')}\n  {h.get('body', '')}"
            for h in hits
        )
    except Exception as exc:
        return f"error: {exc}"
