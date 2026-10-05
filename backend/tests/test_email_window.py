"""Письма по расписанию — только с 09:00 до 21:00 по местному времени
(решение владельца 05.10.2026, lifecycle_emails.email_window_open).

После перевода прогона писем на круглые сутки (05.10.2026, «Важный
транзит») онбординг мог уйти ночью; лунный возврат и дайджест и до того
уходили в 06:00 UTC — в Нью-Йорке это 02:00. Здесь каждый отправитель по
расписанию гоняется ежечасно двое суток (дайджест — неделю) для Владивостока,
Москвы и Нью-Йорка: каждое письмо ушло, один раз и в окне.
"""
from __future__ import annotations

import asyncio
import itertools
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from backend import lifecycle_emails as le
from backend import time_utils
from backend.models import FeatureFlag, PaymentEvent, User

TZS = ("Asia/Vladivostok", "Europe/Moscow", "America/New_York")
START = datetime(2026, 10, 4, 0, 30, tzinfo=timezone.utc)   # воскресенье
_n = itertools.count(1)


@pytest.fixture
def clock(monkeypatch):
    """Подменяет «сейчас» в time_utils (utcnow, local_today) — за ним идут
    все отправители."""
    box = {"t": START}

    class FakeDT(datetime):
        @classmethod
        def now(cls, tz=None):
            return box["t"].astimezone(tz) if tz else box["t"].replace(tzinfo=None)
    monkeypatch.setattr(time_utils, "datetime", FakeDT)
    return box


@pytest.fixture
def mails(monkeypatch, clock):
    """Письма вместо Resend: (адрес, момент UTC)."""
    out: list[tuple[str, datetime]] = []

    async def fake_send(to, subject, html, **kw):
        out.append((to, clock["t"]))
        return True
    monkeypatch.setattr("backend.email_service._send", fake_send)
    return out


def _sweep(clock, run, hours=48):
    for h in range(hours):
        clock["t"] = START + timedelta(hours=h)
        run(clock["t"])


def _user(db, tz, **kw) -> User:
    u = User(email=f"w{next(_n)}@example.com", device_timezone=tz, **kw)
    db.add(u)
    db.commit()
    return u


def _assert_in_window(mails, users, daily=False):
    """Каждому — ровно одно письмо (daily — не больше одного за местные
    сутки, хотя бы одно), и все — в окне 09–21 местного."""
    by = {u.email: u.device_timezone for u in users}
    got = [(to, t) for to, t in mails if to in by]
    for to in by:
        mine = [t.astimezone(ZoneInfo(by[to])).date() for x, t in got if x == to]
        if daily:
            assert mine and len(mine) == len(set(mine)), (to, by[to], mine)
        else:
            assert len(mine) == 1, (to, by[to], mine)
    for to, t in got:
        local = t.astimezone(ZoneInfo(by[to]))
        assert 9 <= local.hour < 21, f"{by[to]}: письмо в {local:%H:%M}"


@pytest.mark.parametrize("utc_hour, tz, open_", [
    (22, "Asia/Vladivostok", False),   # 08:30 местного
    (23, "Asia/Vladivostok", True),    # 09:30
    (10, "Asia/Vladivostok", True),    # 20:30
    (11, "Asia/Vladivostok", False),   # 21:30
    (6, "Europe/Moscow", True),        # 09:30
    (18, "Europe/Moscow", False),      # 21:30
    (6, "America/New_York", False),    # 02:30
    (13, "America/New_York", True),    # 09:30
    (0, "America/New_York", True),     # 20:30
    (1, "America/New_York", False),    # 21:30
])
def test_window_helper(utc_hour, tz, open_):
    now = datetime(2026, 10, 5, utc_hour, 30)
    assert le.email_window_open(SimpleNamespace(device_timezone=tz), None, now) is open_


def test_onboarding_and_purchase(db, mails, clock, monkeypatch):
    """day2 (запасной), day14 и lite_day14 — по одному, в окне."""
    monkeypatch.setattr(le, "_day2_event", lambda chart, user, today: None)
    monkeypatch.setattr(le, "_latest_charts_by_user",
                        lambda db, ids: {i: SimpleNamespace(planets=[], timezone=None) for i in ids})
    users = []
    for tz in TZS:
        users.append(_user(db, tz, tier="free", created_at=(START - timedelta(days=2, hours=1)).replace(tzinfo=None)))
        users.append(_user(db, tz, tier="free", created_at=(START - timedelta(days=14, hours=1)).replace(tzinfo=None)))
        buyer = _user(db, tz, tier="lite", created_at=(START - timedelta(days=60)).replace(tzinfo=None))
        db.add(PaymentEvent(provider="yookassa", inv_id=f"p-{next(_n)}", user_id=buyer.id, tier="lite",
                            period="monthly", amount=100.0, starts_chain=True,
                            created_at=(START - timedelta(days=14, hours=1)).replace(tzinfo=None)))
        users.append(buyer)
    db.commit()
    _sweep(clock, lambda t: le.run_lifecycle_emails(db, t.replace(tzinfo=None)))
    _assert_in_window(mails, users)


def test_transit_alert(db, mails, clock, monkeypatch):
    """«Важный транзит» — по письму в каждый местный день касания, в окне."""
    from backend.day_event import DayEvent
    monkeypatch.setattr("backend.chart_utils.get_primary_chart",
                        lambda db, u: SimpleNamespace(id="c", planets=[{}], timezone=None))
    monkeypatch.setattr("backend.transit.engine.alert_event",
                        lambda c, d, tz: DayEvent(key=f"Pluto:Venus:square:{d}", at_local=datetime.combine(
                            d, datetime.min.time(), ZoneInfo(tz)), transit="Pluto", natal="Venus",
                            aspect="square", score=25, timed=True))
    users = [_user(db, tz, tier="pro") for tz in TZS]
    _sweep(clock, lambda t: le._send_transit_alerts(db, t.replace(tzinfo=None)), hours=24)
    _assert_in_window(mails, users, daily=True)


def _tasks_db(monkeypatch, db):
    from backend import tasks
    monkeypatch.setattr(tasks, "SessionLocal", lambda: db)
    monkeypatch.setattr(db, "close", lambda: None)
    return tasks


def test_lunar_return(db, mails, clock, monkeypatch):
    """Лунный возврат: каждый день — день возврата; одно письмо в местные сутки."""
    tasks = _tasks_db(monkeypatch, db)
    monkeypatch.setattr(tasks, "_get_primary_chart",
                        lambda db, u: SimpleNamespace(id="c", planets=[{}], time_unknown=False, timezone=None))
    monkeypatch.setattr("backend.transit.engine.get_next_lunar_return", lambda natal, d: d)
    users = [_user(db, tz, tier="free") for tz in TZS]
    _sweep(clock, lambda t: tasks.check_lunar_returns(), hours=24)
    _assert_in_window(mails, users, daily=True)


def test_weekly_digest(db, mails, clock, monkeypatch):
    """Дайджест — в местный день недели, в окне, раз в день."""
    tasks = _tasks_db(monkeypatch, db)
    monkeypatch.setattr("backend.chart_utils.get_primary_chart", lambda db, u: None)

    async def fake_digest(user, db_):
        from backend import email_service
        return await email_service._send(user.email, "d", "<p/>")
    monkeypatch.setattr("backend.email_service.send_weekly_digest", fake_digest)
    users = [_user(db, tz, tier="pro", digest_day_of_week=2) for tz in TZS]   # среда
    _sweep(clock, lambda t: tasks.send_weekly_digest_task(), hours=24 * 8)
    _assert_in_window(mails, users)


def test_week_ahead(db, mails, clock, monkeypatch):
    """«Неделя вперёд»: окно «вс 19:00 … пн 12:00» ∩ 09–21 местного."""
    from backend import flags
    from backend import week_ahead as wa
    monkeypatch.setattr("backend.chart_utils.get_primary_chart",
                        lambda db, u: SimpleNamespace(id="c", planets=[{}], timezone=None))
    monkeypatch.setattr(wa, "in_first_week", lambda *a: False)
    monkeypatch.setattr(wa, "week_data", lambda *a: {"calm": False, "title": "t", "range": "r",
                                                     "subject": "s", "preview": "p", "events": []})
    users = [_user(db, tz, tier="free") for tz in TZS]
    db.add(FeatureFlag(key="week_ahead", mode="users", user_ids=[u.id for u in users]))
    db.commit()
    flags.reset_cache()
    try:
        _sweep(clock, lambda t: wa.run_emails(db, t))
    finally:
        flags.reset_cache()
    _assert_in_window(mails, users)


def test_pilot(db, mails, clock, monkeypatch):
    """Пилот: прощание — в окне, ежечасный прогон (tasks.pilot_tick)."""
    tasks = _tasks_db(monkeypatch, db)
    monkeypatch.setattr("backend.pilot.cron._upcoming_windows", lambda db, u: [])
    monkeypatch.setattr("backend.pilot.cron._last_open_date", lambda db, u: None)
    users = [_user(db, tz, tier="pro", pilot_started_at=(START - timedelta(days=28)).replace(tzinfo=None))
             for tz in TZS]
    _sweep(clock, lambda t: tasks.pilot_tick())
    _assert_in_window(mails, users)
