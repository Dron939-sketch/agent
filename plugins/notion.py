"""Notion интеграция — заметки, базы данных, wiki.

Настройка в .env:
  NOTION_API_KEY=secret_...
  NOTION_DEFAULT_PAGE_ID=...  (опционально: корневая страница для заметок)

Получить ключ: https://www.notion.so/my-integrations

Функции:
- notion_search: поиск по Notion workspace
- notion_create_page: создать страницу/заметку
- notion_read_page: прочитать содержимое страницы
- notion_add_to_db: добавить запись в базу данных
"""

from __future__ import annotations

import os
from typing import Any

import aiohttp

from app.core.logging import get_logger
from app.services.tools import tool

logger = get_logger(__name__)

_API_KEY = os.environ.get("NOTION_API_KEY", "")
_DEFAULT_PAGE = os.environ.get("NOTION_DEFAULT_PAGE_ID", "")
_API_URL = "https://api.notion.com/v1"
_NOTION_VERSION = "2022-06-28"


def _configured() -> bool:
    return bool(_API_KEY)


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_API_KEY}",
        "Content-Type": "application/json",
        "Notion-Version": _NOTION_VERSION,
    }


@tool(name="notion_search", description="Поиск страниц и баз данных в Notion.")
async def notion_search(query: str, count: int = 5) -> str:
    """Ищет в Notion workspace по запросу."""
    if not _configured():
        return "Notion не настроен. Добавь NOTION_API_KEY в .env."
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{_API_URL}/search",
                headers=_headers(),
                json={"query": query, "page_size": min(count, 20)},
                timeout=10,
            ) as resp:
                if resp.status != 200:
                    return f"Ошибка: {resp.status}"
                data = await resp.json()

        results = data.get("results", [])
        if not results:
            return f"Ничего не найдено по запросу «{query}»."

        lines: list[str] = []
        for item in results[:count]:
            obj_type = item.get("object", "page")
            title = _extract_title(item)
            url = item.get("url", "")
            lines.append(f"• [{obj_type}] {title}\n  {url}")

        return "\n".join(lines)
    except Exception as exc:
        return f"Ошибка: {exc}"


@tool(name="notion_create_page", description="Создать страницу/заметку в Notion.")
async def notion_create_page(title: str, content: str = "", parent_page_id: str = "") -> str:
    """Создаёт новую страницу. Если parent_page_id пуст — использует NOTION_DEFAULT_PAGE_ID."""
    if not _configured():
        return "Notion не настроен."

    parent_id = parent_page_id or _DEFAULT_PAGE
    if not parent_id:
        return "Укажи parent_page_id или настрой NOTION_DEFAULT_PAGE_ID в .env."

    body: dict[str, Any] = {
        "parent": {"page_id": parent_id},
        "properties": {
            "title": {
                "title": [{"text": {"content": title}}]
            }
        },
    }

    if content:
        # Разбиваем контент на параграфы
        paragraphs = content.split("\n\n") if "\n\n" in content else [content]
        body["children"] = [
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": p.strip()}}]
                },
            }
            for p in paragraphs
            if p.strip()
        ]

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{_API_URL}/pages",
                headers=_headers(),
                json=body,
                timeout=10,
            ) as resp:
                if resp.status not in (200, 201):
                    err = await resp.text()
                    return f"Ошибка создания: {resp.status} {err[:200]}"
                data = await resp.json()
                url = data.get("url", "")
                return f"Страница «{title}» создана. {url}"
    except Exception as exc:
        return f"Ошибка: {exc}"


@tool(name="notion_read_page", description="Прочитать содержимое страницы Notion.")
async def notion_read_page(page_id: str) -> str:
    """Читает блоки контента со страницы."""
    if not _configured():
        return "Notion не настроен."
    try:
        async with aiohttp.ClientSession() as session:
            # Получаем свойства страницы
            async with session.get(
                f"{_API_URL}/pages/{page_id}",
                headers=_headers(),
                timeout=10,
            ) as resp:
                if resp.status != 200:
                    return f"Страница не найдена: {resp.status}"
                page_data = await resp.json()

            title = _extract_title(page_data)

            # Получаем блоки
            async with session.get(
                f"{_API_URL}/blocks/{page_id}/children",
                headers=_headers(),
                params={"page_size": 50},
                timeout=10,
            ) as resp:
                if resp.status != 200:
                    return f"Ошибка чтения блоков: {resp.status}"
                blocks_data = await resp.json()

        blocks = blocks_data.get("results", [])
        content_lines = [f"# {title}", ""]

        for block in blocks:
            text = _extract_block_text(block)
            if text:
                content_lines.append(text)

        return "\n".join(content_lines)
    except Exception as exc:
        return f"Ошибка: {exc}"


@tool(name="notion_add_to_db", description="Добавить запись в базу данных Notion.")
async def notion_add_to_db(database_id: str, title: str, properties: str = "{}") -> str:
    """Добавляет запись. properties — JSON строка с дополнительными полями."""
    if not _configured():
        return "Notion не настроен."

    import json

    try:
        extra_props = json.loads(properties) if properties and properties != "{}" else {}
    except json.JSONDecodeError:
        extra_props = {}

    body: dict[str, Any] = {
        "parent": {"database_id": database_id},
        "properties": {
            "Name": {"title": [{"text": {"content": title}}]},
            **extra_props,
        },
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{_API_URL}/pages",
                headers=_headers(),
                json=body,
                timeout=10,
            ) as resp:
                if resp.status not in (200, 201):
                    err = await resp.text()
                    return f"Ошибка: {resp.status} {err[:200]}"
                data = await resp.json()
                return f"Запись «{title}» добавлена. {data.get('url', '')}"
    except Exception as exc:
        return f"Ошибка: {exc}"


def _extract_title(item: dict) -> str:
    """Извлекает заголовок из Notion object."""
    props = item.get("properties", {})
    for key in ("title", "Name", "name", "Title"):
        prop = props.get(key, {})
        title_arr = prop.get("title", [])
        if title_arr:
            return title_arr[0].get("plain_text", "")
    return "(без названия)"


def _extract_block_text(block: dict) -> str:
    """Извлекает текст из Notion block."""
    block_type = block.get("type", "")
    type_data = block.get(block_type, {})
    rich_text = type_data.get("rich_text", [])

    if not rich_text:
        return ""

    text = "".join(t.get("plain_text", "") for t in rich_text)

    if block_type == "heading_1":
        return f"# {text}"
    if block_type == "heading_2":
        return f"## {text}"
    if block_type == "heading_3":
        return f"### {text}"
    if block_type == "bulleted_list_item":
        return f"• {text}"
    if block_type == "numbered_list_item":
        return f"1. {text}"
    if block_type == "to_do":
        checked = type_data.get("checked", False)
        return f"{'[x]' if checked else '[ ]'} {text}"
    return text
