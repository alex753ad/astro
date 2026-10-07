"""Шаг 9 (термины): «окно» → «период» в пушах и письмах — только под
флагом sky_event. Без флага текст прежний слово в слово (решение владельца
07.10.2026, docs/decisions.md, «Шаг 9»).
"""
import asyncio

import pytest

from backend import email_service as es
from backend.transit.engine import _build_transit_alert_subject


@pytest.fixture
def sent(monkeypatch):
    """Всё, что ушло бы в `_send_info`: тема, превью и тело одной строкой."""
    out = []

    async def fake(to, subject, title, preview, body, *, unsubscribe_url):
        out.append(" ".join((subject, title, preview, body)))
        return True

    monkeypatch.setattr(es, "_send_info", fake)
    return out


def _letters(sky):
    """Все письма с «окном» в тексте — с флагом `sky`."""
    u = "https://x/unsub"
    return [
        es.send_pilot_farewell("a@b", [], unsubscribe_url=u, sky=sky),
        es.send_dormant("a@b", 5, unsubscribe_url=u, sky=sky),
        es.send_dormant("a@b", 10, unsubscribe_url=u, sky=sky),
        es.send_end_of_month_survey("a@b", "https://x/s", unsubscribe_url=u, sky=sky),
        es.send_transit_alert_email("a@b", "Юпитер", "трин", "Солнце", "2026-10-08",
                                    "текст", "тема", "https://x", unsubscribe_url=u, sky=sky),
    ]


def _run(coros):
    async def go():
        for c in coros:
            await c
    asyncio.run(go())


def test_letters_without_flag_keep_window(sent):
    _run(_letters(False))
    assert all("окн" in s for s in sent), [s[:80] for s in sent if "окн" not in s]


def test_letters_under_flag_have_no_window(sent):
    _run(_letters(True))
    assert len(sent) == 5
    for s in sent:
        assert "окн" not in s, s[:200]
        assert "период" in s, s[:200]


def test_alert_subject_harmonious():
    old = _build_transit_alert_subject("Jupiter", "Sun", "trine", "Юпитер")
    new = _build_transit_alert_subject("Jupiter", "Sun", "trine", "Юпитер", sky=True)
    assert old.startswith("Окно открылось:")
    assert new.startswith("Юпитер открывает период:") and "окн" not in new.lower()


# ── Реальный путь рассылки: флаг читается с ORM-карты получателя ─────────────
# Ловушка (docs/handoff.md): `day_event._sky_on` смотрит сессию карты, у копий
# (SimpleNamespace, dict) флаг выключен. Здесь карта — настоящая строка
# NatalChart в базе, флаг — строка feature_flags на получателя, а рассылка
# идёт своей функцией, без подмены `_sky_on`.

from datetime import datetime  # noqa: E402
from datetime import timedelta  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402

from backend import flags  # noqa: E402
from backend.models import FeatureFlag  # noqa: E402
from backend.tests.test_day_event import _fake  # noqa: E402
from backend.tests.test_day_event import sent as push_sent  # noqa: E402,F401 — фикстура
from backend.tests.test_push_upcoming import chart  # noqa: E402,F401 — фикстура
from backend.time_utils import utcnow  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_flags():
    flags.reset_cache()
    yield
    flags.reset_cache()


def _sky_for(db, user):
    db.add(FeatureFlag(key="sky_event", mode="users", user_ids=[user.id]))
    db.commit()
    flags.reset_cache()


@pytest.mark.parametrize("on, title", [(False, "Твоё окно сегодня"), (True, "Твой день в карте")])
def test_push_digest_title_real_send(db, user_free, chart, push_sent, monkeypatch, on, title):  # noqa: F811
    from backend.push import cron
    if on:
        _sky_for(db, user_free)
    a, b = _fake("a"), _fake("b")
    b["ref"] = "b:y"
    monkeypatch.setattr(cron, "_collect_candidates", lambda *x: [a, b])
    cron._process_user(db, user_free)
    assert [p["title"] for p in push_sent] == [title]


@pytest.mark.parametrize("on", [False, True])
def test_transit_alert_real_send(db, user_free, chart, monkeypatch, on):  # noqa: F811
    from backend import lifecycle_emails as le
    from backend.day_event import DayEvent
    if on:
        _sky_for(db, user_free)
    user_free.tier = "pro"
    db.commit()
    monkeypatch.setattr(le, "email_window_open", lambda *a, **k: True)
    ev = DayEvent(key="Jupiter:Sun:trine:2026-10-08T11:00:00",
                  at_local=datetime(2026, 10, 8, 14, 0, tzinfo=ZoneInfo("Europe/Moscow")),
                  transit="Jupiter", natal="Sun", aspect="trine", score=25, timed=True)
    monkeypatch.setattr("backend.transit.engine.alert_event", lambda c, d, tz: ev)
    got = []

    async def fake_send(to, subject, html, **kw):
        got.append((subject, html))
        return True
    monkeypatch.setattr(es, "_send", fake_send)
    assert le._send_transit_alerts(db, datetime(2026, 10, 8, 9, 0)) == 1
    subject, html = got[0]
    if on:
        assert subject.startswith("Юпитер открывает период:") and "Твой период влияния" in html
    else:
        assert subject.startswith("Окно открылось:") and "Твоё окно" in html


@pytest.mark.parametrize("on", [False, True])
def test_digest_subject_real_send(db, user_free, chart, monkeypatch, on):  # noqa: F811
    from backend.tests.test_weekly_digest_week_rule import WEEK, _run
    if on:
        _sky_for(db, user_free)
    monkeypatch.setattr("random.choice", lambda seq: "A")
    _, got = _run(db, user_free, monkeypatch, WEEK)
    assert got["subject"].startswith("Сатурн открывает " + ("период" if on else "окно"))


@pytest.mark.parametrize("on", [False, True])
async def test_pilot_farewell_real_path(db, user_free, chart, monkeypatch, on):  # noqa: F811
    from backend.pilot import cron
    if on:
        _sky_for(db, user_free)
    user_free.pilot_started_at = utcnow() - timedelta(days=28)
    db.commit()
    monkeypatch.setattr("backend.lifecycle_emails.email_window_open", lambda *a, **k: True)
    monkeypatch.setattr(cron, "_upcoming_windows", lambda db, user: [])
    monkeypatch.setattr("backend.push.sender.send_to_user", lambda *a, **k: 0)
    got = []

    async def fake_send(to, subject, title, preview, body, *, unsubscribe_url):
        got.append(" ".join((subject, preview, body)))
        return True
    monkeypatch.setattr(es, "_send_info", fake_send)
    await cron._process(db, user_free)
    assert got, "прощание не ушло"
    assert ("периоды" in got[0]) is on and ("окна" in got[0]) is not on
