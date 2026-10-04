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

from datetime import date, datetime, time, timedelta, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def valid_timezone(name: str | None) -> str | None:
    """Имя пояса IANA, если оно настоящее; иначе None.

    Пояс устройства приходит с клиента (`tz` в запросе, поле настроек) — это
    ввод, а не данные: мусор должен молча откатываться к поясу карты, а не
    ронять ручку.
    """
    if not name or len(name) > 64:
        return None
    try:
        from zoneinfo import ZoneInfo
        ZoneInfo(name)
        return name
    except Exception:
        return None


# Пояс, когда человек о себе ничего не сообщил: ни телефон, ни карта.
# Москва, а не UTC: аудитория русскоязычная, и до 04.10.2026 так уже
# решали уведомления (push/cron.DEFAULT_TZ). Прогноз дня брал UTC — теперь
# Москву, как все.
DEFAULT_TZ = "Europe/Moscow"


def user_tz(request_tz: str | None = None, user=None, chart=None) -> str:
    """ЕДИНЫЙ пояс человека для «сегодня», границы дня и показа времени.

    Порядок (решения владельца 23–24.09.2026, общий с 04.10.2026 для всех
    разделов — шаг 2 аудита, docs/audit_unified_model.md):
    `tz` запроса (приложение и веб шлют пояс устройства, `withTz`) →
    `users.device_timezone` (последний присланный, им живут уведомления) →
    пояс карты → Москва. Мусор на любой ступени молча пропускается.

    ⚠️ До 04.10.2026 способов было шесть: лента и планер пропускали
    `device_timezone`, прогноз дня падал в UTC, PDF брал Москву, письма —
    UTC сервера. Около полуночи разделы называли разные «сегодня». Новый
    раздел берёт пояс ТОЛЬКО отсюда.

    Возвращает имя IANA: его едят и `ZoneInfo`, и `pytz.timezone`, и ключи
    кэшей.
    """
    for name in (request_tz, getattr(user, "device_timezone", None), getattr(chart, "timezone", None)):
        if valid_timezone(name):
            return name
    return DEFAULT_TZ


def local_today(tz: str, now: datetime | None = None) -> date:
    """Местная дата в поясе `tz` (имя IANA). `now` — aware, для тестов."""
    from zoneinfo import ZoneInfo
    return (now or datetime.now(timezone.utc)).astimezone(ZoneInfo(tz)).date()


def local_day(d: date, tz: str) -> tuple[datetime, datetime]:
    """Границы местных суток `d` в UTC, aware: [начало, начало следующих).

    Через `datetime.combine(..., tzinfo=ZoneInfo)`, а не «полночь минус
    смещение»: в день перевода часов сутки не равны 24 часам. pytz сюда
    не подставлять — с ним `tzinfo=` даёт местное среднее время (LMT).
    """
    from zoneinfo import ZoneInfo
    z = ZoneInfo(tz)
    start = datetime.combine(d, time(), z).astimezone(timezone.utc)
    end = datetime.combine(d + timedelta(days=1), time(), z).astimezone(timezone.utc)
    return start, end


def utc_naive_to_local(naive: datetime, tz: str) -> datetime:
    """Наивный UTC (так отдают движки транзитов и домов) → aware местное."""
    from zoneinfo import ZoneInfo
    return naive.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(tz))
