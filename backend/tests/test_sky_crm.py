"""CRM под флагом sky_event (задание 4.12, PR а): строки — касания ядра в
местных датах клиента; письмо и бриф — на событие, касания словами без «~»."""
from datetime import date, datetime, timezone
from types import SimpleNamespace

from backend.crm import dashboard_router as crm
from backend.crm.brief_prompt import _fmt_transits
from backend.sky import SkyEvent, Touch


def _t(at: datetime) -> Touch:
    return Touch(at_utc=at, orb=0.0, exact=True, retrograde=False, transit_sign="Aries", transit_degree=10.0)


def _ev(key, transit, natal, touches, start, end, passes=None) -> SkyEvent:
    return SkyEvent(key=key, transit=transit, natal=natal, aspect="square",
                    start_utc=start, end_utc=end, passes=passes or [(start, end)],
                    touches=touches, closest=touches[0] if touches else _t(start),
                    score=1.0, level="major", tone="tense",
                    natal_sign="Cancer", natal_degree=10.0, natal_house=None)


U = lambda *a: datetime(*a, tzinfo=timezone.utc)
# Касание 07.10 22:30 UTC — во Владивостоке (+10) уже 08.10.
SAT = _ev("sat", "Saturn", "Sun", [_t(U(2026, 10, 7, 22, 30)), _t(U(2026, 10, 20, 3))],
          U(2026, 9, 1), U(2026, 12, 1),
          passes=[(U(2026, 9, 1), U(2026, 10, 12)), (U(2026, 10, 16), U(2026, 12, 1))])
STATION = _ev("jup", "Jupiter", "Moon", [], U(2026, 10, 1), U(2026, 10, 30))
CHART = SimpleNamespace(id="c", timezone="Asia/Vladivostok")


def _patch(monkeypatch):
    monkeypatch.setattr("backend.sky.sky_events", lambda chart, s, e: [SAT, STATION])


def test_rows_are_touches_in_client_local_dates(monkeypatch):
    _patch(monkeypatch)
    rows = crm.crm_events(CHART, date(2026, 10, 8), date(2026, 10, 31), sky=True)
    # Станция без касания — без строки; петля — строка на каждое касание.
    assert [(r.transit_planet, r.peak_date) for r in rows] == [("Saturn", "2026-10-08"), ("Saturn", "2026-10-20")]
    assert crm.important(rows) == rows


def test_touch_outside_local_window_dropped(monkeypatch):
    _patch(monkeypatch)
    # 07.10 по UTC, но 08.10 по местному — в окно «по 07.10» не входит.
    rows = crm.crm_events(CHART, date(2026, 10, 1), date(2026, 10, 7), sky=True)
    assert rows == []


def test_month_letter_one_row_per_event_with_all_touches(monkeypatch):
    _patch(monkeypatch)
    rows = crm._month_transits(CHART, date(2026, 10, 8), sky=True)
    assert len(rows) == 1
    assert rows[0]["when"] == "8 октября и 20 октября 2026"


def test_brief_touches_are_exact_without_tilde():
    text = _fmt_transits([{"transit_planet": "Saturn", "aspect_type": "square", "natal_planet": "Sun",
                           "touches": "8 октября и 20 октября 2026", "period": "1 сентября — 1 декабря 2026"}])
    assert "~" not in text and "точно 8 октября и 20 октября 2026" in text
