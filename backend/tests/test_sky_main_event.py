"""Главное событие дня из ядра (задание 4.2, флаг sky_event). Карта
вымышленная, как в test_sky.py."""
import asyncio
import importlib.util
import types
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from backend import day_event as de
from backend import flags
from backend.lifecycle_emails import ALERT_KIND, _alert_sent_nearby
from backend.models import EmailSentLog, FeatureFlag, NatalChart
from backend.tests.test_sky import CHART

_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _flags():
    flags.reset_cache()
    yield
    flags.reset_cache()


def test_station_day_main_event_is_another():
    """18.10.2027 Плутон разворачивается в 1,6° от Сатурна — касания нет:
    главное событие дня — другое, Плутона среди кандидатов нет."""
    d, tz = date(2027, 10, 18), "Europe/Moscow"
    cands = de._candidates(CHART, d, ZoneInfo(tz), sky=True)
    assert not [c for c in cands if c.transit == "Pluto"]
    ev = de.main_event(CHART, d, tz, "08:00", "22:00", sky=True)
    assert ev.key == "Moon:Saturn:trine:2027-10-18T16:21"


def test_flag_is_read_through_chart_session(db, user_free):
    chart = NatalChart(user_id=user_free.id, birth_date="1991-03-08", birth_time="06:40",
                       birth_place="Moscow", latitude=55.75, longitude=37.62,
                       timezone="Europe/Moscow", planets=CHART["planets"], houses=[], aspects=[])
    db.add(chart)
    db.commit()
    assert de._sky_on(chart) is False
    db.add(FeatureFlag(key="sky_event", mode="users", user_ids=[user_free.id]))
    db.commit()
    flags.reset_cache()
    assert de._sky_on(chart) is True
    assert de._sky_on(CHART) is False          # не из базы — выключен


def test_alert_not_repeated_when_minute_shifts(db, user_free):
    """В день включения флага минута касания у ядра может сдвинуться на 1–2:
    письмо о том же касании второй раз не уходит."""
    db.add(EmailSentLog(user_id=user_free.id, kind=ALERT_KIND, ref="Pluto:Venus:square:2026-10-08T11:00",
                        sent_at=datetime(2026, 10, 8, 6, 15)))
    db.commit()
    assert _alert_sent_nearby(db, user_free.id, "Pluto:Venus:square:2026-10-08T11:02")
    assert _alert_sent_nearby(db, user_free.id, "Pluto:Venus:square:2026-10-07T23:59")
    assert not _alert_sent_nearby(db, user_free.id, "Pluto:Venus:trine:2026-10-08T11:02")
    assert not _alert_sent_nearby(db, user_free.id, "Pluto:Venus:square:2027-02-01T05:00")


def test_c1_c2_zero_under_flag(monkeypatch):
    """Прогон согласованности под флагом: главное событие есть в ленте (c1) и
    оно первый факт прогноза дня (c2) — неделя, Москва."""
    spec = importlib.util.spec_from_file_location("consistency_eval", _ROOT / "scripts" / "consistency_eval.py")
    ce = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ce)
    import chat_eval
    import backend.ephemeris.geo as geo

    async def fake_geo(place):
        return types.SimpleNamespace(latitude=55.75, longitude=37.62, timezone="Europe/Moscow")
    monkeypatch.setattr(geo, "geocode_place", fake_geo)
    monkeypatch.setattr(de, "_sky_on", lambda chart: True)
    stored, _, unknown = asyncio.run(chat_eval._chart({"date": "1991-03-08", "time": "06:40", "place": "Moscow"}))
    tz, d0 = "Europe/Moscow", date(2026, 10, 3)
    chart = ce._ns(stored, "test-sky-c1", tz, unknown)
    days = [date(2026, 10, 3 + i) for i in range(7)]
    feed = ce._feed(chart, date(2026, 10, 1), date(2026, 10, 11), d0, "premium")
    c1, c2 = ce.Check(), ce.Check()
    ce.check_c1_c2(c1, c2, chart, feed, days, tz)
    assert c1.compared and not c1.bad, c1.bad
    assert c2.compared and not c2.bad, c2.bad
