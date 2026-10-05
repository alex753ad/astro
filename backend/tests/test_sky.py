"""Ядро транзитов backend/sky.py (задание 4.1, аудит 8.2). Карта вымышленная,
как в test_day_event.py и test_exact_touch.py: 08.03.1991 03:40 UTC, Москва."""
import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend import sky
from backend.day_event import points
from backend.ephemeris.calculator import calculate_full_chart

_ROOT = Path(__file__).resolve().parents[2]
_FULL, _ = calculate_full_chart(datetime(1991, 3, 8, 3, 40), 55.75, 37.62, house_system="placidus")
CHART = {
    "planets": [{"name": p.name, "longitude": p.longitude, "sign": p.sign} for p in _FULL.planets],
    "ascendant": {"longitude": _FULL.ascendant.longitude, "sign": _FULL.ascendant.sign},
    "midheaven": {"longitude": _FULL.midheaven.longitude, "sign": _FULL.midheaven.sign},
}


def _utc(*a):
    return datetime(*a, tzinfo=timezone.utc)


def _one(key_prefix, frm, to, chart=CHART):
    evs = [e for e in sky.compute(chart, frm, to) if e.key.startswith(key_prefix)]
    assert len(evs) == 1, [e.key for e in evs]
    return evs[0]


def test_pluto_station_at_saturn_is_not_a_touch():
    """Станция Плутона 18.10.2027 в 1,6° от Сатурна — проход петли без касания."""
    e = _one("Pluto:Saturn:conjunction:", _utc(2027, 10, 1), _utc(2027, 11, 1))
    assert e.passes[-1][0].date().isoformat() == "2027-09-05"
    assert e.end_utc.date().isoformat() == "2027-11-28"
    assert all(t.at_utc.year < 2027 for t in e.touches)
    assert e.key == "Pluto:Saturn:conjunction:2025-03-11"


def test_jupiter_trine_venus_station_is_not_a_touch():
    """Станция Юпитера 13.04.2027 в 0,08° от Венеры — не касание. По правилу
    петли это второй проход события с касанием 16.09.2026 (вошёл в орб с той
    стороны, с которой вышел), поэтому closest = то касание."""
    e = _one("Jupiter:Venus:trine:", _utc(2027, 4, 1), _utc(2027, 4, 30))
    assert [t.at_utc.date().isoformat() for t in e.touches] == ["2026-09-16"]
    assert [p[0].date().isoformat() for p in e.passes] == ["2026-09-09", "2027-03-13"]
    assert e.closest is e.touches[0] and e.closest.exact


def test_closest_without_touch_o3(monkeypatch):
    """О3: событие без касания — только при сближении ≤ 0,5°. При полном скане
    такого не бывает (планета в итоге проходит точку, петля склеивается),
    поэтому скан урезан: виден только проход станции."""
    monkeypatch.setattr(sky, "MAX_GROW", 1)
    monkeypatch.setitem(sky.PAD_DAYS, "Jupiter", 30)
    monkeypatch.setitem(sky.PAD_DAYS, "Pluto", 30)
    e = _one("Jupiter:Venus:trine:", _utc(2027, 4, 1), _utc(2027, 4, 30))
    assert not e.touches and not e.closest.exact
    assert e.closest.orb == pytest.approx(0.08, abs=0.01)
    assert e.key == "Jupiter:Venus:trine:2027-04-13"
    # Плутон у Сатурна — 1,6° > 0,5°: не событие.
    assert not [x for x in sky.compute(CHART, _utc(2027, 10, 1), _utc(2027, 11, 1))
                if x.key.startswith("Pluto:Saturn:conjunction:")]


def test_mercury_loop_is_one_event():
    """Петля Меркурия к Плутону: одно событие, три касания, перерыв в passes."""
    e = _one("Mercury:Pluto:conjunction:", _utc(2026, 10, 15), _utc(2026, 12, 5))
    assert [(a.isoformat(), b.isoformat()) for a, b in e.passes] == [
        ("2026-10-17T08:58:00+00:00", "2026-10-30T08:22:00+00:00"),
        ("2026-11-28T09:10:00+00:00", "2026-12-01T04:31:00+00:00"),
    ]
    assert [t.at_utc.isoformat() for t in e.touches] == [
        "2026-10-21T00:16:00+00:00", "2026-10-27T08:44:00+00:00", "2026-11-29T19:12:00+00:00"]
    assert [t.retrograde for t in e.touches] == [False, True, False]
    assert e.local("Europe/Moscow").touch_days[0].isoformat() == "2026-10-21"


@pytest.mark.parametrize("prefix,windows", [
    # Окно на последнем проходе петли и окно на первом — одно событие.
    ("Mercury:Pluto:conjunction:", [(_utc(2026, 11, 29), _utc(2026, 11, 30)),
                                    (_utc(2026, 10, 18), _utc(2026, 10, 19))]),
    # Окно в перерыве петли Плутона (вне орба) и на её последнем проходе.
    ("Pluto:Saturn:conjunction:", [(_utc(2027, 5, 1), _utc(2027, 5, 31)),
                                   (_utc(2027, 11, 1), _utc(2027, 11, 30))]),
])
def test_key_does_not_depend_on_window(prefix, windows):
    """Первое касание ищется по всему событию, а не в чанке."""
    a, b = (_one(prefix, *w) for w in windows)
    assert a.to_dict() == b.to_dict()


def test_cached_chunks_equal_direct_compute(monkeypatch):
    """Чанки sky:v1 (через JSON) — те же события, что прямой расчёт."""
    monkeypatch.setattr(sky.sky_cache, "_redis", None)
    monkeypatch.setattr(sky.sky_cache, "_local", {})
    frm, to = _utc(2026, 10, 25), _utc(2026, 11, 5)
    chart = {**CHART, "id": "test-sky"}
    first = sky.sky_events(chart, frm, to)
    assert sorted(sky.sky_cache._local) == ["sky:v1:test-sky:2026-10", "sky:v1:test-sky:2026-11"]
    assert [e.to_dict() for e in sky.sky_events(chart, frm, to)] == [e.to_dict() for e in first]
    assert {e.key for e in first} == {e.key for e in sky.compute(chart, frm, to)}


def test_no_birth_time_no_moon_asc_mc():
    frm, to = _utc(2026, 10, 1), _utc(2026, 11, 1)
    with_time = {e.natal for e in sky.compute(CHART, frm, to)}
    assert {"Moon", "Ascendant", "Midheaven"} <= with_time
    evs = sky.compute({**CHART, "time_unknown": True}, frm, to)
    assert evs and not {e.natal for e in evs} & {"Moon", "Ascendant", "Midheaven"}
    assert all(e.natal_house is None for e in evs)


def test_core_equals_cb_truth():
    """Сверка с независимой истиной cB (scripts/consistency_eval.truth_transits).
    Друг друга они не импортируют — иначе ядро проверяло бы само себя.
    Истина берёт верх минутного интервала, ядро — пол минуты (как
    `_find_exact_aspect`): допуск 2 минуты."""
    assert "consistency_eval" not in (_ROOT / "backend" / "sky.py").read_text(encoding="utf-8")
    script = (_ROOT / "scripts" / "consistency_eval.py").read_text(encoding="utf-8")
    assert "backend.sky" not in script and "import sky" not in script
    spec = importlib.util.spec_from_file_location("consistency_eval", _ROOT / "scripts" / "consistency_eval.py")
    ce = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ce)

    frm, to = _utc(2026, 10, 5), _utc(2026, 12, 5)
    truth = ce.truth_transits(points(CHART), frm.replace(tzinfo=None), to.replace(tzinfo=None))
    core = sky.compute(CHART, frm, to)
    near = lambda a, b: abs(a - b) <= timedelta(minutes=2)
    assert len(core) == len(truth) > 100
    for x in truth:
        same = [e for e in core if (e.transit, e.natal, e.aspect) == x["key"]
                and len(e.touches) == len(x["touches"])
                and all(near(t.at_utc, r) for t, r in zip(e.touches, x["touches"]))
                and (not x["start_known"] or near(e.start_utc, x["start"]))
                and (not x["end_known"] or near(e.end_utc, x["end"]))]
        assert len(same) == 1, x
