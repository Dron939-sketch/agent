"""Email интеграция: отправка и чтение почты.

Настройка в .env:
  EMAIL_IMAP_HOST=imap.gmail.com
  EMAIL_IMAP_PORT=993
  EMAIL_SMTP_HOST=smtp.gmail.com
  EMAIL_SMTP_PORT=587
  EMAIL_ADDRESS=freddy@example.com
  EMAIL_PASSWORD=app-password-here

Для Gmail: используй App Password (не основной пароль).
"""

from __future__ import annotations

import asyncio
import email
import os
import smtplib
from email.header import decode_header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from app.core.logging import get_logger
from app.services.tools import tool

logger = get_logger(__name__)

_IMAP_HOST = os.environ.get("EMAIL_IMAP_HOST", "")
_IMAP_PORT = int(os.environ.get("EMAIL_IMAP_PORT", "993"))
_SMTP_HOST = os.environ.get("EMAIL_SMTP_HOST", "")
_SMTP_PORT = int(os.environ.get("EMAIL_SMTP_PORT", "587"))
_EMAIL_ADDR = os.environ.get("EMAIL_ADDRESS", "")
_EMAIL_PASS = os.environ.get("EMAIL_PASSWORD", "")


def _is_configured() -> bool:
    return bool(_EMAIL_ADDR and _EMAIL_PASS)


def _decode_mime_header(header: str) -> str:
    """Декодирует MIME header (может быть base64/utf-8)."""
    parts = decode_header(header)
    result = []
    for data, charset in parts:
        if isinstance(data, bytes):
            result.append(data.decode(charset or "utf-8", errors="replace"))
        else:
            result.append(data)
    return " ".join(result)


@tool(name="email_inbox", description="Показать последние входящие письма.")
async def email_inbox(count: int = 5) -> str:
    """Читает последние count писем из INBOX."""
    if not _is_configured():
        return "Email не настроен. Добавь EMAIL_ADDRESS, EMAIL_PASSWORD, EMAIL_IMAP_HOST в .env."

    def _fetch():
        import imaplib

        mail = imaplib.IMAP4_SSL(_IMAP_HOST, _IMAP_PORT)
        mail.login(_EMAIL_ADDR, _EMAIL_PASS)
        mail.select("INBOX")

        _, data = mail.search(None, "ALL")
        ids = data[0].split()
        if not ids:
            mail.logout()
            return "Входящие пусты."

        recent = ids[-min(count, len(ids)):]
        messages: list[str] = []

        for msg_id in reversed(recent):
            _, msg_data = mail.fetch(msg_id, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
            if not msg_data or not msg_data[0]:
                continue
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)
            frm = _decode_mime_header(msg.get("From", ""))
            subj = _decode_mime_header(msg.get("Subject", "(без темы)"))
            date = msg.get("Date", "")
            messages.append(f"• {subj}\n  От: {frm}\n  Дата: {date}")

        mail.logout()
        return "\n\n".join(messages) if messages else "Нет писем."

    try:
        result = await asyncio.get_event_loop().run_in_executor(None, _fetch)
        return f"Последние письма:\n\n{result}"
    except Exception as exc:
        return f"Ошибка чтения почты: {exc}"


@tool(name="email_send", description="Отправить email.")
async def email_send(to: str, subject: str, body: str) -> str:
    """Отправляет письмо через SMTP.

    Args:
        to: email получателя
        subject: тема письма
        body: текст письма
    """
    if not _is_configured():
        return "Email не настроен."

    if not _SMTP_HOST:
        return "SMTP не настроен (EMAIL_SMTP_HOST)."

    def _send():
        msg = MIMEMultipart()
        msg["From"] = _EMAIL_ADDR
        msg["To"] = to
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain", "utf-8"))

        with smtplib.SMTP(_SMTP_HOST, _SMTP_PORT) as server:
            server.starttls()
            server.login(_EMAIL_ADDR, _EMAIL_PASS)
            server.send_message(msg)

    try:
        await asyncio.get_event_loop().run_in_executor(None, _send)
        return f"Письмо отправлено: {to} — {subject}"
    except Exception as exc:
        return f"Ошибка отправки: {exc}"


@tool(name="email_search", description="Поиск писем по теме или отправителю.")
async def email_search(query: str, count: int = 5) -> str:
    """Ищет письма по теме или отправителю."""
    if not _is_configured():
        return "Email не настроен."

    def _search():
        import imaplib

        mail = imaplib.IMAP4_SSL(_IMAP_HOST, _IMAP_PORT)
        mail.login(_EMAIL_ADDR, _EMAIL_PASS)
        mail.select("INBOX")

        # Пробуем поиск по теме и по отправителю
        criteria = f'(OR SUBJECT "{query}" FROM "{query}")'
        _, data = mail.search(None, criteria)
        ids = data[0].split()

        if not ids:
            mail.logout()
            return f"Ничего не найдено по запросу «{query}»."

        recent = ids[-min(count, len(ids)):]
        messages: list[str] = []

        for msg_id in reversed(recent):
            _, msg_data = mail.fetch(msg_id, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
            if not msg_data or not msg_data[0]:
                continue
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)
            frm = _decode_mime_header(msg.get("From", ""))
            subj = _decode_mime_header(msg.get("Subject", "(без темы)"))
            messages.append(f"• {subj} — от {frm}")

        mail.logout()
        return "\n".join(messages) if messages else "Ничего не найдено."

    try:
        result = await asyncio.get_event_loop().run_in_executor(None, _search)
        return result
    except Exception as exc:
        return f"Ошибка поиска: {exc}"
