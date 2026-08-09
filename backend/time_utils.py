"""Текущее время в UTC — без deprecated datetime.utcnow().

datetime.utcnow() возвращает naive datetime (без tzinfo) и помечен как
deprecated с Python 3.12: он молча использует системный часовой пояс для
вычисления UTC вместо явного tzinfo, что исторически было источником багов на
серверах с непустым TZ. Прямая замена на datetime.now(timezone.utc) даёт
AWARE datetime — а в проекте все колонки `Column(DateTime)` без
`timezone=True` и всё сравнение дат построено на naive-значениях; подмешать
aware datetime в это означало бы падение на первом же сравнении
(TypeError: can't compare offset-naive and offset-aware datetimes) в SQLite и
молчаливую порчу данных в Postgres.

utcnow() возвращает то же самое значение, что и datetime.utcnow() — naive
datetime в UTC — но без вызова deprecated метода.
"""
from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
