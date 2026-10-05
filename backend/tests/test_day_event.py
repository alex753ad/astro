"""Главное событие дня и лимит пушей (флаг push_day_event).

Правило — docs/notifications.md, «Главное событие дня и лимит пушей».
Без флага тик обязан вести себя как до него: потолок мягких 1/48ч на месте,
в push_sends ничего не пишется (docs/flags.md, п.4).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
import pytz

from zoneinfo import ZoneInfo

from backend import day_event as de
from backend import flags
from backend.day_event import (
    LUNATION_ADVICE, MOON_ADVICE, NATAL_PLANETS, PLANET_ADVICE, RETURN_MIN_SCORE, RETURN_TEXT,
    SLOW, TONE_ADVICE, DayEvent, advice, main_event, title, week_top,
)
from backend.models import FeatureFlag, PushSend, PushSentLog, UserActivityDay
from backend.push import cron
from backend.push.cron import in_send_window
from backend.tests.test_push_upcoming import chart  # noqa: F401 — фикстура
from backend.time_utils import utcnow

TZ = pytz.timezone("Europe/Moscow")
MORNING = TZ.localize(datetime(2026, 9, 10, 8, 30))


@pytest.fixture(autouse=True)
def _fresh_flags():
    flags.reset_cache()
    yield
    flags.reset_cache()


@pytest.fixture
def flag_on(db, user_free):
    db.add(FeatureFlag(key="push_day_event", mode="users", user_ids=[user_free.id]))
    db.commit()
    flags.reset_cache()


@pytest.fixture
def only_daily(db, user_free):
    """Только «Прогноз дня»: значимые события сняли бы потолок и без флага."""
    user_free.push_planner = False
    user_free.push_key_transits = False
    user_free.push_moon_phases = False
    db.commit()


@pytest.fixture
def sent(monkeypatch):
    out = []
    monkeypatch.setattr(cron, "send_to_user", lambda db_, uid, payload: out.append(payload) or 1)

    class _Frozen(datetime):
        @classmethod
        def now(cls, tz_=None):
            return MORNING.astimezone(tz_) if tz_ else MORNING

    monkeypatch.setattr(cron, "datetime", _Frozen)
    return out


def _soft_capped_yesterday(db, user):
    db.add(PushSentLog(user_id=user.id, kind="daily", ref_key="2026-09-09",
                       sent_at=utcnow() - timedelta(hours=1)))
    db.commit()


class TestMainEvent:
    def test_same_answer_every_call_and_inside_window(self, chart):
        seen = 0
        for i in range(10):
            d = date(2026, 9, 10) + timedelta(days=i)
            a = main_event(chart, d, "Europe/Moscow", "08:00", "22:00")
            assert a == main_event(chart, d, "Europe/Moscow", "08:00", "22:00")
            if a is None:
                continue
            seen += 1
            assert a.at_local.date() == d
            assert in_send_window(a.at_local, "08:00", "22:00") or (a.transit in SLOW and not a.timed)
        assert seen, "за 10 дней у карты должно найтись хоть одно событие"

    def test_title_names_time_only_when_timed(self, chart):
        for i in range(10):
            ev = main_event(chart, date(2026, 9, 10) + timedelta(days=i), "Europe/Moscow", "08:00", "22:00")
            if ev:
                assert title(ev).startswith(f"{ev.at_local:%H:%M} · ") == ev.timed
                assert "✦" not in title(ev)
                assert advice(ev)


class TestTexts:
    """Тексты согласованы владельцем 01.10.2026: совет до 60 знаков."""

    def test_every_advice_fits_collapsed_shade(self):
        texts = [t for table in PLANET_ADVICE.values() for row in table.values() for t in row]
        texts += [*TONE_ADVICE.values(), *LUNATION_ADVICE.values()]
        assert len(texts) == 5 * 36 + 3 + 2
        assert len(set(texts)) == len(texts), "дословных повторов быть не должно"
        assert all(len(t) <= 60 for t in texts), [t for t in texts if len(t) > 60]

    def test_every_table_covers_every_natal_point(self):
        for planet, table in PLANET_ADVICE.items():
            assert set(table) == set(NATAL_PLANETS) | {"Ascendant", "Midheaven"}, planet
            assert all(len(row) == 3 for row in table.values()), planet

    def test_moon_by_tone_other_planets_general(self):
        ev = DayEvent(key="k", at_local=datetime(2026, 10, 1, 15, 1, tzinfo=timezone.utc),
                      transit="Moon", natal="Moon", aspect="square", score=1, timed=True)
        assert title(ev) == "15:01 · Луна к твоей Луне"
        assert advice(ev) == MOON_ADVICE["Moon"][1]
        mars = DayEvent(**{**ev.__dict__, "transit": "Mars", "aspect": "trine"})
        assert advice(mars) == PLANET_ADVICE["Mars"]["Moon"][0]
        jupiter = DayEvent(**{**ev.__dict__, "transit": "Jupiter", "aspect": "trine"})
        assert advice(jupiter) == TONE_ADVICE["harmonious"]
        slow = DayEvent(**{**ev.__dict__, "transit": "Saturn", "natal": "Sun", "timed": False})
        assert title(slow) == "Сатурн к твоему Солнцу"
        nm = DayEvent(**{**ev.__dict__, "transit": "new_moon", "natal": None, "aspect": None})
        assert (title(nm), advice(nm)) == ("15:01 · Новолуние", LUNATION_ADVICE["new_moon"])


class TestFlagOff:
    def test_soft_cap_kept_and_nothing_recorded(self, db, user_free, chart, only_daily, sent):
        _soft_capped_yesterday(db, user_free)
        assert cron._process_user(db, user_free) == 0
        assert sent == []
        assert db.query(PushSend).count() == 0


class TestFlagOn:
    def test_morning_every_day_despite_soft_cap(self, db, user_free, chart, only_daily, flag_on, sent):
        _soft_capped_yesterday(db, user_free)
        assert cron._process_user(db, user_free) == 1
        # У тестовой карты в этот день есть главное событие — заголовок его.
        assert " · " in sent[0]["title"] and "✦" not in sent[0]["title"]
        assert len(sent[0]["body"]) <= 60
        assert [r.slot for r in db.query(PushSend).all()] == ["morning"]

    def test_cap_blocks_third_push(self, db, user_free, chart, only_daily, flag_on, sent):
        for slot in ("evening", "evening"):  # любые два содержательных
            db.add(PushSend(user_id=user_free.id, local_date=MORNING.date(), slot=slot))
        db.commit()
        assert cron._process_user(db, user_free) == 0
        assert sent == []
        assert db.query(PushSentLog).filter(PushSentLog.kind == "daily").count() == 0


# ── Утро — только главное событие; planner_month — вечером (01.10.2026) ──
def _fake(kind):
    return {"kind": kind, "ref": f"{kind}:x", "priority": "significant", "weight": 90,
            "frag": kind, "title": kind, "body": kind, "url": "/planner"}


@pytest.fixture
def other_kinds(monkeypatch, db, user_free):
    user_free.push_moon_phases = False
    db.commit()
    monkeypatch.setattr(cron, "_triple_touch_candidates", lambda *a: [_fake("triple")])
    monkeypatch.setattr(cron, "_transit_entry_candidates", lambda *a: [_fake("transit")])
    monkeypatch.setattr(cron, "_four_degree_candidates", lambda *a: [_fake("transit_approach")])
    monkeypatch.setattr(cron, "_planner_month_candidates", lambda *a: [_fake("planner_month")])


def _logged(db):
    return {r.kind for r in db.query(PushSentLog).all()}


class TestMorningOnlyMainEvent:
    def test_flag_off_glues_as_before(self, db, user_free, chart, other_kinds, sent):
        assert cron._process_user(db, user_free) == 1
        assert sent[0]["title"] == "Твоё окно сегодня"

    def test_flag_on_sends_only_day_event_and_marks_others(self, db, user_free, chart, other_kinds, flag_on, sent):
        assert cron._process_user(db, user_free) == 1
        assert len(sent) == 1 and " · " in sent[0]["title"]
        assert sent[0]["title"] != "Твоё окно сегодня"
        assert {"daily", "triple", "transit", "transit_approach"} <= _logged(db)
        assert "planner_month" not in _logged(db), "его отправит вечер"

    def test_planner_month_replaces_evening(self, db, user_free, chart, other_kinds, flag_on, sent):
        evening = TZ.localize(datetime(2026, 9, 10, 20, 30))
        assert cron._send_evening(db, user_free, chart, evening, day_on=True) == 1
        assert sent[0]["title"] == "planner_month"
        assert {"planner_month", "tomorrow"} <= _logged(db)
        assert cron._send_evening(db, user_free, chart, evening, day_on=True) == 0

    def test_upcoming_follows_the_same_rule(self, db, user_free, chart, other_kinds, flag_on, sent):
        kinds = {e["kind"] for e in cron.collect_upcoming(db, user_free, 3)["events"]}
        assert kinds & cron.MUTED_UNDER_DAY_EVENT == set()
        assert "planner_month" in kinds and "tomorrow" not in kinds


# ── Возврат (флаг push_return) ──
@pytest.fixture
def return_on(db, user_free):
    db.add(FeatureFlag(key="push_return", mode="users", user_ids=[user_free.id]))
    db.commit()
    flags.reset_cache()


@pytest.fixture
def saturn_next_week(monkeypatch):
    ev = DayEvent(key="k", at_local=TZ.localize(datetime(2026, 9, 14, 16, 49)), transit="Saturn",
                  natal="Moon", aspect="square", score=37.5, timed=True)
    monkeypatch.setattr("backend.day_event.week_top", lambda *a: ev)


def _active(db, user, days_ago):
    db.add(UserActivityDay(user_id=user.id, day=MORNING.date() - timedelta(days=days_ago),
                           platform="app", flags=[]))
    db.commit()


class TestReturn:
    def test_dormant_gets_event_of_the_week_once(self, db, user_free, chart, only_daily, return_on,
                                                 saturn_next_week, sent):
        _active(db, user_free, 5)
        assert cron._process_user(db, user_free) == 1
        assert sent[0]["title"] == "14 сентября · Сатурн к твоей Луне"
        assert sent[0]["body"] == RETURN_TEXT
        assert cron._apply_return(db, user_free, chart, MORNING.date(), [{"kind": "daily"}]) is None

    @pytest.mark.parametrize("days_ago", [None, 4])
    def test_no_return_without_break_or_history(self, db, user_free, chart, only_daily, return_on,
                                                saturn_next_week, sent, days_ago):
        if days_ago is not None:
            _active(db, user_free, days_ago)
        cron._process_user(db, user_free)
        assert sent and sent[0]["body"] != RETURN_TEXT

    def test_flag_off(self, db, user_free, chart, only_daily, saturn_next_week, sent):
        _active(db, user_free, 10)
        cron._process_user(db, user_free)
        assert sent and sent[0]["body"] != RETURN_TEXT

    def test_week_top_respects_threshold(self, chart):
        ev = week_top(chart, date(2026, 9, 10), "Europe/Moscow", "08:00", "22:00")
        assert ev is None or ev.score >= RETURN_MIN_SCORE
        assert len(RETURN_TEXT) <= 60


# ── Углы карты: ASC/MC — не куспиды 1 и 10 (04.10.2026) ──
# У «равных домов» куспид 10 ≠ MC, у «целых знаков» куспиды 1 и 10 — начала
# знаков. Карта вымышленная, координаты заданы — без геокодера.
_SYSTEMS = ("placidus", "equal", "whole_sign")


def _angle_chart(system: str):
    import types
    from backend.ephemeris.calculator import calculate_full_chart
    full, _ = calculate_full_chart(datetime(1991, 3, 8, 3, 40), 55.75, 37.62, house_system=system)
    return types.SimpleNamespace(
        id=f"angles-{system}", time_unknown=False, timezone="Europe/Moscow",
        planets=[{"name": p.name, "longitude": p.longitude, "sign": p.sign} for p in full.planets],
        houses=[{"number": h.number, "degree": h.degree, "sign": h.sign} for h in full.houses],
        ascendant={"longitude": full.ascendant.longitude}, midheaven={"longitude": full.midheaven.longitude},
    )


def _sep(a: float, b: float) -> float:
    return abs((a - b + 180) % 360 - 180)


@pytest.mark.parametrize("system", _SYSTEMS)
def test_angles_are_chart_angles_not_cusps(system):
    from backend.day_event import _targets
    c = _angle_chart(system)
    t = {p["name"]: p["longitude"] for p in _targets(c)}
    assert t["Ascendant"] == c.ascendant["longitude"]
    assert t["Midheaven"] == c.midheaven["longitude"]


def test_fixture_cusps_differ_from_angles():
    """Без этого тест ниже прошёл бы и на старом коде: у этих систем куспид
    обязан отличаться от угла."""
    eq, ws = _angle_chart("equal"), _angle_chart("whole_sign")
    assert _sep(eq.houses[9]["degree"], eq.midheaven["longitude"]) > 1
    assert _sep(ws.houses[0]["degree"], ws.ascendant["longitude"]) > 1
    assert _sep(ws.houses[9]["degree"], ws.midheaven["longitude"]) > 1


@pytest.mark.parametrize("system", _SYSTEMS)
def test_touch_is_to_the_angle(system):
    """Касание к ASC/MC в точный момент — к углу карты (орб ≈ 0), где бы ни
    стоял куспид."""
    from zoneinfo import ZoneInfo
    from backend.day_event import _candidates
    from backend.ephemeris.aspects import ASPECTS
    from backend.ephemeris.calculator import PLANETS, _calc_planet_position, _datetime_to_jd

    c = _angle_chart(system)
    angles = {"Ascendant": c.ascendant["longitude"], "Midheaven": c.midheaven["longitude"]}
    seen = set()
    for i in range(4):
        for ev in _candidates(c, date(2026, 10, 1) + timedelta(days=i), ZoneInfo("Europe/Moscow")):
            if ev.natal not in angles:
                continue
            at = ev.at_local.astimezone(timezone.utc).replace(tzinfo=None)
            lon = _calc_planet_position(PLANETS[ev.transit], round(_datetime_to_jd(at), 6))[0]
            assert abs(_sep(lon, angles[ev.natal]) - ASPECTS[ev.aspect]) < 0.1, (system, ev)
            seen.add(ev.natal)
    assert seen == set(angles), f"{system}: за 4 дня нет касаний к углам — тест ничего не проверил"


# ── Одна шкала и узлы (шаг 5 аудита, 05.10.2026) ──

@pytest.mark.parametrize("tp, np_, asp, level", [
    ("Moon", "Sun", "conjunction", "low"),        # Луна в ленте всегда low (балл 9)
    ("Mars", "Sun", "conjunction", "high"),       # 3 × 3 × 3 = 27
    ("Saturn", "Jupiter", "trine", "medium"),     # 5 × 1 × 2 = 10
    ("Sun", "Saturn", "square", "low"),           # 2 × 1 × 2.5 = 5
    ("Mercury", "Midheaven", "opposition", "high"),  # 2 × 3 × 2.5 = 15
])
def test_feed_level_by_score(tp, np_, asp, level):
    assert de.feed_level(tp, np_, asp) == level


def test_nodes_only_conjunction_and_opposition():
    assert de.counts("North Node", "conjunction") and de.counts("North Node", "opposition")
    assert not de.counts("North Node", "trine") and not de.counts("North Node", "square")
    assert de.counts("Venus", "trine")


def test_node_axis_texts():
    at = datetime(2026, 10, 3, 10, 15, tzinfo=ZoneInfo("Europe/Moscow"))
    ev = de.DayEvent(key="k", at_local=at, transit="Venus", natal="North Node",
                     aspect="conjunction", score=6, timed=True)
    assert de.title(ev) == "10:15 · Венера на оси узлов"
    assert de.advice(ev) == "Побудь с теми, рядом с кем хочется расти."
    slow = de.DayEvent(**{**ev.__dict__, "transit": "Saturn", "aspect": "opposition"})
    assert de.advice(slow) == de.TONE_ADVICE["tense"]
