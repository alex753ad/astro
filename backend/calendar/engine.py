"""backend/calendar/engine.py

Движок общего астро-календаря (бесплатный уровень).
Вычисляет ключевые события месяца БЕЗ натальной карты:
  - Новолуния и Полнолуния
  - Ингрессы планет (смена знака)
  - Точные аспекты между медленными планетами
"""

from __future__ import annotations

import os
from datetime import date, timedelta
from dataclasses import dataclass, field
from typing import Optional
import swisseph as swe

EPHE_PATH = os.getenv("EPHE_PATH", "./data/ephe")
swe.set_ephe_path(EPHE_PATH)

PLANET_IDS = {
    "Sun":     swe.SUN,
    "Moon":    swe.MOON,
    "Mercury": swe.MERCURY,
    "Venus":   swe.VENUS,
    "Mars":    swe.MARS,
    "Jupiter": swe.JUPITER,
    "Saturn":  swe.SATURN,
    "Uranus":  swe.URANUS,
    "Neptune": swe.NEPTUNE,
    "Pluto":   swe.PLUTO,
}

ZODIAC_SIGNS = [
    "Овен","Телец","Близнецы","Рак","Лев","Дева",
    "Весы","Скорпион","Стрелец","Козерог","Водолей","Рыбы",
]

SLOW_PLANETS  = ["Jupiter","Saturn","Uranus","Neptune","Pluto"]
WATCH_PLANETS = ["Sun","Mercury","Venus","Mars","Jupiter","Saturn"]

MAJOR_ASPECTS = {"соединение":0,"секстиль":60,"квадрат":90,"трин":120,"оппозиция":180}
ORB = 1.5


@dataclass
class CalendarEvent:
    date:        str
    time:        str
    type:        str        # new_moon | full_moon | ingress | aspect
    planet:      str
    sign:        Optional[str] = None
    planet2:     Optional[str] = None
    aspect_name: Optional[str] = None
    description: str = ""
    emoji:       str = "⭐"

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None}


# ── utils ─────────────────────────────────────────────────────────────────────

def _jd(d: date, hour: float = 12.0) -> float:
    return swe.julday(d.year, d.month, d.day, hour)

def _jd_to_dt(jd: float) -> tuple[str, str]:
    y, mo, d, h_float = swe.revjul(jd)
    h = int(h_float)
    m = int((h_float - h) * 60)
    return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}", f"{h:02d}:{m:02d}"

def _lon(jd: float, planet: str) -> float:
    r, _ = swe.calc_ut(jd, PLANET_IDS[planet], swe.FLG_SWIEPH)
    return r[0]

def _sign(lon: float) -> str:
    return ZODIAC_SIGNS[int(lon // 30) % 12]

def _diff(a: float, b: float) -> float:
    d = (a - b) % 360
    return d - 360 if d > 180 else d


# ── Moon phases ───────────────────────────────────────────────────────────────

def _find_phase(jd_start: float, jd_end: float, target: float) -> list[float]:
    results, step = [], 0.5
    jd, prev = jd_start, None
    while jd < jd_end:
        ang = (_lon(jd, "Moon") - _lon(jd, "Sun")) % 360
        val = (ang - target) % 360
        if val > 180:
            val -= 360
        if prev is not None and prev * val < 0:
            lo, hi = jd - step, jd
            for _ in range(48):  # достаточно итераций для точности ~1 сек
                mid = (lo + hi) / 2
                v = ((_lon(mid, "Moon") - _lon(mid, "Sun")) % 360 - target) % 360
                if v > 180:
                    v -= 360
                if v > 0:
                    hi = mid
                else:
                    lo = mid
            results.append((lo + hi) / 2)
        prev = val
        jd += step
    return results

def get_moon_phases(year: int, month: int) -> list[CalendarEvent]:
    from calendar import monthrange
    _, days = monthrange(year, month)
    # hour=0 первого дня до hour=0 первого дня следующего месяца
    jd0 = _jd(date(year, month, 1), 0)
    if month == 12:
        jd1 = _jd(date(year + 1, 1, 1), 0)
    else:
        jd1 = _jd(date(year, month + 1, 1), 0)
    events = []
    for target, etype, emoji in [
        (0,   "new_moon",  "🌑"),
        (180, "full_moon", "🌕"),
    ]:
        found = _find_phase(jd0, jd1, target)
        for jd in found:
            dt, tm = _jd_to_dt(jd)
            sign  = _sign(_lon(jd, "Moon"))
            label = "Новолуние" if etype == "new_moon" else "Полнолуние"
            events.append(CalendarEvent(
                date=dt, time=f"{tm} UTC", type=etype,
                planet="Moon", sign=sign, emoji=emoji,
                description=f"{label} в {sign}",
            ))
    return events


# ── Planet ingresses ──────────────────────────────────────────────────────────

def get_ingresses(year: int, month: int) -> list[CalendarEvent]:
    from calendar import monthrange
    _, days = monthrange(year, month)
    d_start = date(year, month, 1)
    d_end   = date(year, month, days)
    events  = []

    for planet in WATCH_PLANETS:
        step_h = 2 if planet in ("Sun","Mercury","Venus","Mars") else 24
        step_d = step_h / 24
        jd  = _jd(d_start, 0)
        jd1 = _jd(d_end, 24)
        prev_sign = _sign(_lon(jd, planet))

        while jd < jd1:
            jd += step_d
            cur_sign = _sign(_lon(jd, planet))
            if cur_sign != prev_sign:
                # бисекция
                lo, hi = jd - step_d, jd
                for _ in range(20):
                    mid = (lo + hi) / 2
                    (_hi := mid) if _sign(_lon(mid, planet)) == prev_sign else (_lo := mid)
                    # simplified bisection
                    if _sign(_lon(mid, planet)) == prev_sign:
                        lo = mid
                    else:
                        hi = mid
                exact_jd = (lo + hi) / 2
                dt, tm = _jd_to_dt(exact_jd)
                events.append(CalendarEvent(
                    date=dt, time=f"{tm} UTC", type="ingress",
                    planet=planet, sign=cur_sign, emoji="➡️",
                    description=f"{planet} входит в {cur_sign}",
                ))
                prev_sign = cur_sign

    return events


# ── Slow planet aspects ───────────────────────────────────────────────────────

def get_slow_aspects(year: int, month: int) -> list[CalendarEvent]:
    from calendar import monthrange
    from itertools import combinations
    _, days = monthrange(year, month)
    jd0 = _jd(date(year, month, 1), 0)
    jd1 = _jd(date(year, month, days), 24)
    events = []

    pairs = list(combinations(SLOW_PLANETS, 2))
    for p1, p2 in pairs:
        for asp_name, asp_angle in MAJOR_ASPECTS.items():
            jd, step = jd0, 1.0
            prev_diff = None
            while jd < jd1:
                l1, l2  = _lon(jd, p1), _lon(jd, p2)
                raw     = abs((l1 - l2) % 360)
                if raw > 180: raw = 360 - raw
                orb = raw - asp_angle

                if prev_diff is not None and abs(orb) < ORB and prev_diff * orb < 0:
                    # точный момент
                    lo, hi = jd - step, jd
                    for _ in range(15):
                        mid = (lo + hi) / 2
                        r = abs((_lon(mid,p1) - _lon(mid,p2)) % 360)
                        if r > 180: r = 360 - r
                        o = r - asp_angle
                        if o > 0: hi = mid
                        else: lo = mid
                    exact = (lo + hi) / 2
                    dt, tm = _jd_to_dt(exact)
                    events.append(CalendarEvent(
                        date=dt, time=f"{tm} UTC", type="aspect",
                        planet=p1, planet2=p2, aspect_name=asp_name,
                        emoji="⚡" if asp_name in ("квадрат","оппозиция") else "✨",
                        description=f"{p1} {asp_name} {p2}",
                    ))
                prev_diff = orb
                jd += step

    return sorted(events, key=lambda e: e.date)


# ── Main entry point ──────────────────────────────────────────────────────────

def get_monthly_calendar(year: int, month: int) -> list[dict]:
    """Полный список ключевых событий месяца для общего календаря."""
    events: list[CalendarEvent] = []
    events.extend(get_moon_phases(year, month))
    events.extend(get_ingresses(year, month))
    events.extend(get_slow_aspects(year, month))
    events.sort(key=lambda e: (e.date, e.time))
    return [e.to_dict() for e in events]
