"""Владивосток 07.10.2026: главное событие без времени (roadmap, «Мелкие ошибки»).

Воспроизведение на синтетическом касании: карта из Consistency — секрет, её
касаний здесь нет. Медленная планета, касание в 23:49 местного — после
quiet_from 22:00, вне окна отправки. main_event берёт его главным (медленным
можно и вне окна), но с timed=False — заголовок без времени. Правило:
docs/notifications.md, «у медленной планеты вне окна — без времени».
"""
from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from backend import day_event as de

VLAT = ZoneInfo("Asia/Vladivostok")
DAY = date(2026, 10, 7)


def _touch(hh, mm, transit="Saturn"):
    at = datetime(2026, 10, 7, hh, mm, tzinfo=VLAT)
    return de.DayEvent(key=f"{transit}:Sun:square:{at:%H:%M}", at_local=at, transit=transit,
                       natal="Sun", aspect="square", score=de.score(transit, "Sun", "square"), timed=True)


@pytest.mark.parametrize("hh, mm, timed", [(23, 49, False), (21, 49, True)])
def test_slow_touch_time_shown_only_inside_window(monkeypatch, hh, mm, timed):
    monkeypatch.setattr(de, "_candidates", lambda *a, **k: [_touch(hh, mm)])
    ev = de.main_event(object(), DAY, "Asia/Vladivostok", "08:00", "22:00")
    assert ev is not None and ev.at_local.date() == DAY
    assert ev.timed is timed
    assert de.title(ev).startswith(f"{hh:02d}:{mm:02d} · ") is timed


def test_fast_touch_outside_window_is_dropped(monkeypatch):
    monkeypatch.setattr(de, "_candidates", lambda *a, **k: [_touch(23, 49, "Mars")])
    assert de.main_event(object(), DAY, "Asia/Vladivostok", "08:00", "22:00") is None
