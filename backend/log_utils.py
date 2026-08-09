"""Маскирование персональных данных в логах.

Логи уходят в json-file драйвер Docker, читаются любым, у кого есть доступ к
диску или к сокету Docker, и попадают в бэкапы. Email — персональные данные;
для сервиса, обрабатывающего ПДн граждан РФ, полный адрес в логе это претензия
по 152-ФЗ, а для расследования инцидента его и не нужно: рядом всегда есть
user.id, а домен и первая буква позволяют узнать «тот самый» адрес глазами.
"""
from __future__ import annotations

import re


def mask_email(email: str | None) -> str:
    """a***@gmail.com — безопасный для лога вид адреса."""
    if not email or "@" not in email:
        return "<no-email>"
    local, _, domain = email.partition("@")
    return f"{local[:1]}***@{domain}"


_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")


def mask_emails_in_text(text: str) -> str:
    """Заменяет все адреса внутри произвольной строки.

    Нужно там, где адрес приезжает не отдельным полем, а внутри готового
    сообщения: текст исключения, breadcrumb Sentry, тело запроса.
    """
    return _EMAIL_RE.sub(lambda m: mask_email(m.group(0)), text)
