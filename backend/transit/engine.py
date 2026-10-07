"""Transit calculation engine — v2.

Key changes vs v1:
- TransitEvent now has start_date / peak_date / end_date (full period in orb)
- get_planet_positions_for_date(date) returns all transit planet longitudes
  so the frontend can show planet movement on the wheel

Algorithm:
1. Scan the period in FAST_STEP_HOURS steps for all planets (the Moon needs it);
   SLOW_STEP_HOURS is only the bracket for refining the exact moment.
2. When a (transit_planet, natal_planet, aspect) combo enters orb → open a window.
3. While still in orb → update current orb; track minimum (peak).
4. When it leaves orb → close the window, emit one TransitEvent with the full span.
5. At query time, filter by active date rather than exact date.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, date, timezone
from typing import Optional
from urllib.parse import quote

from backend.ephemeris.calculator import (
    PLANETS,
    ZODIAC_SIGNS,
    _datetime_to_jd,
    _longitude_to_sign,
    _calc_planet_position,
    _find_house,
)
from backend.ephemeris.aspects import ASPECTS, _angular_distance

logger = logging.getLogger("astro.transit")

# ── Planet classification ──
FAST_PLANETS  = {"Sun", "Moon", "Mercury", "Venus", "Mars"}
SLOW_PLANETS  = {"Jupiter", "Saturn", "Uranus", "Neptune", "Pluto", "North Node"}

FAST_STEP_HOURS = 4
SLOW_STEP_HOURS = 24

# Transit orbs (tighter than natal)
TRANSIT_ORBS = {
    "conjunction": 2.0,
    "sextile":     1.5,
    "square":      2.0,
    "trine":       1.5,
    "opposition":  2.0,
}


@dataclass
class TransitEvent:
    """A transit aspect with full period of activity."""
    start_date:     str             # first day orb is active   (ISO)
    peak_date:      str             # day of tightest orb       (ISO)
    end_date:       str             # last day orb is active    (ISO)
    transit_planet: str
    transit_sign:   str             # sign on peak_date
    transit_degree: float           # degree-in-sign of transit planet at peak
    natal_planet:   str
    natal_sign:     str
    aspect_type:    str
    peak_orb:       float           # tightest orb (degrees)
    exact_date:     Optional[str] = None   # precise peak datetime (ISO)
    applying:       bool = True
    # E2 (Free-витрина транзитов): значимость + топ-2, разблокированные для Free
    significant:    bool = False           # медленная планета к личной натальной
    free_unlocked:  bool = False           # входит в топ-2 значимых (AI-разбор для Free)
    # Касания нет: ближайшее сближение ВНУТРИ окна (станция рядом с точкой), а
    # корня разности долгот нет (_find_exact_aspect). У окна, обрезанного краем
    # скана, минимум на краю — касание может быть за ним, это не no_touch.
    # Лента, /transits и PDF такие события не показывают до решения владельца
    # о подписи «ближе всего» (аудит, О3); главное событие и прогнозы и так
    # берут только exact_date.
    no_touch:       bool = False

    # ── convenience ──
    @property
    def date(self) -> str:
        """Alias so old code using .date still works (returns peak_date)."""
        return self.peak_date

    @property
    def orb(self) -> float:
        """Alias for peak_orb."""
        return self.peak_orb


@dataclass
class _Window:
    """Internal: tracks an open transit window while planet is in orb."""
    transit_planet: str
    natal_planet:   str
    aspect_type:    str
    natal_sign:     str
    start_dt:       datetime
    peak_dt:        datetime
    peak_orb:       float
    peak_sign:      str
    peak_deg:       float
    applying:       bool
    last_dt:        datetime        # updated each step while in orb


def calculate_transits(
    natal_planets: list[dict],
    from_date: date,
    to_date: date,
    orb_filter: Optional[float] = None,
    planet_filter: Optional[list[str]] = None,
) -> list[TransitEvent]:
    """Calculate all transit periods for a natal chart over a date range.

    Returns one TransitEvent per (transit_planet, natal_planet, aspect) passage,
    with start_date/peak_date/end_date covering the full active window.
    """
    natal_positions = {
        p["name"]: {"longitude": p["longitude"], "sign": p["sign"]}
        for p in natal_planets
    }

    transit_planet_names = set(PLANETS.keys()) - {"North Node"}
    if planet_filter:
        transit_planet_names &= set(planet_filter)

    # open_windows[(t_name, n_name, aspect_name)] = _Window
    open_windows: dict[tuple, _Window] = {}
    closed_events: list[TransitEvent] = []

    # Extend scan slightly beyond requested range to catch windows that close after to_date
    scan_end = datetime(to_date.year, to_date.month, to_date.day, 23, 59, 59) + timedelta(days=3)
    current   = datetime(from_date.year, from_date.month, from_date.day, 0, 0, 0)

    while current <= scan_end:
        jd = _datetime_to_jd(current)

        for t_name in transit_planet_names:
            t_id = PLANETS[t_name]
            t_lon, _, _, t_speed = _calc_planet_position(t_id, round(jd, 6))
            t_sign, t_deg       = _longitude_to_sign(t_lon)

            for n_name, n_data in natal_positions.items():
                n_lon  = n_data["longitude"]
                angle  = _angular_distance(t_lon, n_lon)

                for aspect_name, exact_angle in ASPECTS.items():
                    max_orb = TRANSIT_ORBS[aspect_name]
                    if orb_filter is not None:
                        max_orb = min(max_orb, orb_filter)

                    orb = abs(angle - exact_angle)
                    key = (t_name, n_name, aspect_name)

                    if orb <= max_orb:
                        if key not in open_windows:
                            # Open new window
                            open_windows[key] = _Window(
                                transit_planet=t_name,
                                natal_planet=n_name,
                                aspect_type=aspect_name,
                                natal_sign=n_data["sign"],
                                start_dt=current,
                                peak_dt=current,
                                peak_orb=orb,
                                peak_sign=t_sign,
                                peak_deg=t_deg,
                                applying=t_speed >= 0,
                                last_dt=current,
                            )
                        else:
                            w = open_windows[key]
                            w.last_dt = current
                            if orb < w.peak_orb:
                                w.peak_orb  = orb
                                w.peak_dt   = current
                                w.peak_sign = t_sign
                                w.peak_deg  = t_deg
                                w.applying  = t_speed >= 0
                    else:
                        if key in open_windows:
                            # Close window → emit event
                            w = open_windows.pop(key)
                            # Only emit if window overlaps requested range
                            if w.last_dt.date() >= from_date and w.start_dt.date() <= to_date:
                                step_h = FAST_STEP_HOURS if t_name in FAST_PLANETS else SLOW_STEP_HOURS
                                exact_dt = _find_exact_aspect(t_id, n_lon, exact_angle, w.peak_dt, step_h)
                                closed_events.append(_make_event(w, exact_dt))

        # Step size: use fast step so Moon is caught properly
        current += timedelta(hours=FAST_STEP_HOURS)

    # Close any windows still open at scan end
    for key, w in open_windows.items():
        t_name = w.transit_planet
        if w.last_dt.date() >= from_date and w.start_dt.date() <= to_date:
            t_id = PLANETS[t_name]
            n_lon = natal_positions[w.natal_planet]["longitude"]
            exact_angle = ASPECTS[w.aspect_type]
            step_h = FAST_STEP_HOURS if t_name in FAST_PLANETS else SLOW_STEP_HOURS
            exact_dt = _find_exact_aspect(t_id, n_lon, exact_angle, w.peak_dt, step_h)
            closed_events.append(_make_event(w, exact_dt))

    closed_events.sort(key=lambda e: (e.peak_date, e.peak_orb))

    logger.info(
        "Calculated %d transit periods for %s → %s",
        len(closed_events), from_date, to_date,
    )
    return closed_events


def _make_event(w: _Window, exact_dt: Optional[datetime]) -> TransitEvent:
    return TransitEvent(
        start_date=w.start_dt.strftime("%Y-%m-%d"),
        peak_date=w.peak_dt.strftime("%Y-%m-%d"),
        end_date=w.last_dt.strftime("%Y-%m-%d"),
        transit_planet=w.transit_planet,
        transit_sign=w.peak_sign,
        transit_degree=round(w.peak_deg, 1),
        natal_planet=w.natal_planet,
        natal_sign=w.natal_sign,
        aspect_type=w.aspect_type,
        peak_orb=round(w.peak_orb, 4),
        exact_date=exact_dt.strftime("%Y-%m-%dT%H:%M") if exact_dt else None,
        applying=w.applying,
        no_touch=exact_dt is None and w.start_dt < w.peak_dt < w.last_dt,
    )


# E2 — значимость транзита: медленная планета к личной натальной планете
_SIGNIFICANT_TRANSIT_PLANETS = {"Jupiter", "Saturn", "Uranus", "Neptune", "Pluto"}
_PERSONAL_NATAL_PLANETS = {"Sun", "Moon", "Mercury", "Venus", "Mars"}
FREE_UNLOCKED_TRANSITS = 2  # сколько значимых транзитов открыто для Free


def is_significant_pair(transit_planet: str, natal_planet: str) -> bool:
    """Значим ли транзит (медленная планета к личной натальной)."""
    return (
        transit_planet in _SIGNIFICANT_TRANSIT_PLANETS
        and natal_planet in _PERSONAL_NATAL_PLANETS
    )


def _is_significant(e: TransitEvent) -> bool:
    return is_significant_pair(e.transit_planet, e.natal_planet)


def mark_transit_significance(events: list[TransitEvent]) -> None:
    """Проставить significant/free_unlocked на месте.

    Значимые = медленная планета к личной. Из них топ-N по минимальному орбу
    получают free_unlocked=True (AI-разбор открыт для Free). Tier-независимо —
    результат можно кэшировать.
    """
    for e in events:
        e.significant = _is_significant(e)
        e.free_unlocked = False
    significant = [e for e in events if e.significant]
    top = sorted(significant, key=lambda e: e.peak_orb)[:FREE_UNLOCKED_TRANSITS]
    for e in top:
        e.free_unlocked = True


def get_planet_positions_for_date(query_date: date) -> list[dict]:
    """Return current ecliptic longitudes for all transit planets on a given date.

    Used by the frontend to show planet positions on the natal wheel for a
    selected day, so the user can see where planets are moving.

    Returns list of:
      {name, longitude, sign, degree_in_sign, retrograde, glyph}
    """
    dt = datetime(query_date.year, query_date.month, query_date.day, 12, 0, 0)
    jd = _datetime_to_jd(dt)

    GLYPHS = {
        "Sun": "☉", "Moon": "☽", "Mercury": "☿", "Venus": "♀",
        "Mars": "♂", "Jupiter": "♃", "Saturn": "♄", "Uranus": "♅",
        "Neptune": "♆", "Pluto": "♇", "North Node": "☊",
    }

    result = []
    for name, planet_id in PLANETS.items():
        lon, _, _, speed = _calc_planet_position(planet_id, round(jd, 6))
        sign, deg = _longitude_to_sign(lon)
        result.append({
            "name":          name,
            "longitude":     round(lon, 4),
            "sign":          sign,
            "degree_in_sign": round(deg, 4),
            "retrograde":    speed < 0,
            "glyph":         GLYPHS.get(name, "?"),
        })
    return result


def _signed(lon: float, natal_longitude: float, angle: float, side: int) -> float:
    """Знаковая разность (t − n) ∓ угол, приведённая к (−180°, 180°]."""
    return (lon - natal_longitude - side * angle + 180.0) % 360.0 - 180.0


def _find_exact_aspect(
    transit_planet_id: int,
    natal_longitude: float,
    target_angle: float,
    approx_dt: datetime,
    window_hours: int,
) -> Optional[datetime]:
    """Момент ТОЧНОГО касания в [approx_dt ± window_hours] — корень знаковой
    разности долгот `(t − n) ∓ угол`, ближайший к `approx_dt`, до минуты.
    Касания нет — None.

    ⚠️ Не минимум орба (так было до 05.10.2026, аудит 8.1). Станция в 1,6° от
    натальной точки — минимум орба, но не касание: разность не меняет знак.
    Минимум выдавался за «точный», и главное событие дня, письмо «Важный
    транзит» и лента называли касание, которого нет. Минимум движка
    (`calculate_transits`) остаётся только подсказкой, где искать корень.
    Единственный помощник «точного» в проекте — своих поисков не заводить.
    """
    def f(dt: datetime, side: int) -> float:
        lon, _, _, _ = _calc_planet_position(transit_planet_id, round(_datetime_to_jd(dt), 6))
        return _signed(lon, natal_longitude, target_angle, side)

    start = approx_dt - timedelta(hours=window_hours)
    step = timedelta(hours=window_hours) / 12
    best: Optional[datetime] = None
    for side in ((1,) if target_angle in (0, 180) else (1, -1)):
        prev_t, prev_v = start, f(start, side)
        for i in range(1, 25):
            t = start + i * step
            v = f(t, side)
            # |v| < 90 — смена знака у 0°, а не скачок ±180° при приведении.
            if (prev_v > 0) != (v > 0) and abs(prev_v) < 90 and abs(v) < 90:
                lo, hi = prev_t, t
                while hi - lo > timedelta(seconds=2):
                    mid = lo + (hi - lo) / 2
                    lo, hi = (mid, hi) if (f(mid, side) > 0) == (prev_v > 0) else (lo, mid)
                root = lo + (hi - lo) / 2
                if best is None or abs(root - approx_dt) < abs(best - approx_dt):
                    best = root
            prev_t, prev_v = t, v
    if best is None:
        return None
    # Секунды отбрасываются, как до 05.10.2026: минута входит в ключи главного
    # события и письма «Важный транзит» — округление сдвинуло бы их и повторило письмо.
    return best.replace(second=0, microsecond=0)


def window_events(chart, from_date: date, to_date: date, orb_filter: float | None = None,
                  planet_filter: list[str] | None = None, sky: bool = False,
                  tz: str | None = None) -> list[dict]:
    """События окна для `GET /chart/{id}/transits` — поля `TransitEventSchema`.

    Вынесено из ручки (06.10.2026), чтобы прогон согласованности (cB,
    /transits) проверял ровно то, что отдаёт веб, теми же окнами, что листает
    таймлайн. Синхронная (Swiss Ephemeris): из ручки — через `to_thread`.
    `sky` — флаг sky_event (4.8): события ядра, `_sky_window_events`."""
    if sky:
        return _sky_window_events(chart, from_date, to_date, planet_filter, tz or "UTC")
    from backend.chart_points import planets as natal_planets
    events = calculate_transits(
        # chart_points: без времени рождения — без натальной Луны (шаг 3).
        natal_planets=natal_planets(chart), from_date=from_date, to_date=to_date,
        orb_filter=orb_filter, planet_filter=planet_filter,
    )
    # Без касания (станция рядом с точкой) — не показываем, пока нет подписи
    # «ближе всего» (аудит, О3): иначе веб назвал бы минимум орба пиком.
    events = [e for e in events if not e.no_touch]
    # E2: пометить значимые (топ-2 → free_unlocked) — tier-независимо, кэшируется
    mark_transit_significance(events)
    return [{
        "start_date": e.start_date, "peak_date": e.peak_date, "end_date": e.end_date,
        "transit_planet": e.transit_planet, "transit_sign": e.transit_sign,
        "transit_degree": e.transit_degree, "natal_planet": e.natal_planet,
        "natal_sign": e.natal_sign, "aspect_type": e.aspect_type,
        "peak_orb": e.peak_orb, "exact_date": e.exact_date, "applying": e.applying,
        "significant": e.significant, "free_unlocked": e.free_unlocked,
    } for e in events]


def _sky_window_events(chart, from_date: date, to_date: date,
                       planet_filter: list[str] | None, tz: str) -> list[dict]:
    """/transits под флагом sky_event (задание 4.8): карточка на каждое
    касание ядра, чья МЕСТНАЯ дата в окне (как лента, О4); проход без касания
    — без карточки (О3).

    * `start_date` / `end_date` — всего события, местные, окном не режутся;
    * `peak_date` — UTC-дата касания: только ключ (разбор — `find_event`,
      ссылка письма «Важный транзит» — `event={UTC-дата}-…`, `eventKey` веба);
    * `touch_date` — местная дата касания: ей веб показывает, группирует и
      сортирует карточки (решение владельца 06.10.2026); `exact_date` —
      местное время касания «YYYY-MM-DDTHH:MM» (веб выводит его как есть);
    * точки — `day_event.points` (с ASC/MC; без времени рождения — без них).
    `orb_filter` не нужен: у касания орб ≈ 0, веб его не шлёт."""
    from zoneinfo import ZoneInfo

    from backend.sky import sky_events
    from backend.time_utils import local_day

    z = ZoneInfo(tz)
    s, e = local_day(from_date, tz)[0], local_day(to_date, tz)[1]
    out = []
    for ev in sky_events(chart, s, e):
        if planet_filter and ev.transit not in planet_filter:
            continue
        for t in ev.touches:
            if not (s <= t.at_utc < e):
                continue
            loc = t.at_utc.astimezone(z)
            out.append({
                "start_date": ev.start_utc.astimezone(z).date().isoformat(),
                "peak_date": t.at_utc.date().isoformat(),
                "end_date": ev.end_utc.astimezone(z).date().isoformat(),
                "touch_date": loc.date().isoformat(),
                "transit_planet": ev.transit, "transit_sign": t.transit_sign,
                "transit_degree": t.transit_degree, "natal_planet": ev.natal,
                "natal_sign": ev.natal_sign, "aspect_type": ev.aspect,
                "peak_orb": t.orb, "exact_date": loc.strftime("%Y-%m-%dT%H:%M"),
                # Как у движка: «applying» = планета идёт прямо.
                "applying": not t.retrograde,
                "significant": is_significant_pair(ev.transit, ev.natal),
                "free_unlocked": False,
            })
    # Топ значимых окна — как mark_transit_significance; орб касаний ≈ 0 у
    # всех, поэтому при равенстве — раньше по времени.
    for r in sorted((r for r in out if r["significant"]),
                    key=lambda r: (r["peak_orb"], r["exact_date"]))[:FREE_UNLOCKED_TRANSITS]:
        r["free_unlocked"] = True
    return sorted(out, key=lambda r: (r["exact_date"], r["transit_planet"], r["natal_planet"]))


def compute_exact_facts(
    transit_planet: str,
    natal_planet: str,
    aspect_type: str,
    peak_date: date,
    natal_profile: dict,
) -> dict:
    """Пересчитать на бэкенде все факты одного транзитного события для промпта.

    LLM не вычисляет астрономию — эта функция считает всё через Swiss Ephemeris,
    клиентские значения (transit_sign/orb/exact_date из тела запроса) сюда не
    попадают вообще, используются только как идентификатор события.

    Возвращает dict: transit_sign, transit_degree, transit_house,
    transit_retrograde, natal_sign, natal_degree, natal_house, exact_orb,
    exact_date (ISO date | None), period_start, period_end (ISO date | None).
    """
    from backend.transit.house_passages import _extract_cusps

    planet_id = PLANETS.get(transit_planet)
    target_angle = ASPECTS.get(aspect_type)
    cusps = _extract_cusps(natal_profile)

    natal_entry = next(
        (p for p in natal_profile.get("planets", []) if p.get("name") == natal_planet),
        None,
    )
    natal_lon = natal_entry.get("longitude") if natal_entry else None

    facts = {
        "transit_sign": None, "transit_degree": None, "transit_house": None,
        "transit_retrograde": False,
        "natal_sign": natal_entry.get("sign") if natal_entry else None,
        # Из долготы, не degree_in_sign: у ASC/MC (chart_points.targets) его нет.
        "natal_degree": round(natal_lon % 30, 2) if natal_lon is not None else None,
        "natal_house": natal_entry.get("house") if natal_entry else None,
        "exact_orb": None, "exact_date": None,
        "period_start": None, "period_end": None,
    }

    if planet_id is None or natal_lon is None or target_angle is None:
        return facts

    def _lon_at(d: date) -> float:
        dt = datetime(d.year, d.month, d.day, 12, 0, 0)
        jd = _datetime_to_jd(dt)
        lon, _, _, _ = _calc_planet_position(planet_id, round(jd, 6))
        return lon

    dt_noon = datetime(peak_date.year, peak_date.month, peak_date.day, 12, 0, 0)

    # Ищем точный момент аспекта СНАЧАЛА: для быстрых планет (~1°/сутки) пик
    # может случиться в любой час дня, а не ровно в полдень — если брать факты
    # (знак/градус/орб) на полдень вместо истинного момента, орб может
    # разойтись на ~1° с тем, что реально показывает таймлайн.
    exact_dt = _find_exact_aspect(planet_id, natal_lon, target_angle, dt_noon, window_hours=120)
    fact_dt = exact_dt or dt_noon
    if exact_dt:
        facts["exact_date"] = exact_dt.date().isoformat()

    jd_fact = _datetime_to_jd(fact_dt)
    transit_lon, _, _, speed = _calc_planet_position(planet_id, round(jd_fact, 6))
    sign, deg = _longitude_to_sign(transit_lon)

    facts["transit_sign"] = sign
    facts["transit_degree"] = round(deg, 2)
    facts["transit_retrograde"] = speed < 0
    facts["transit_house"] = _find_house(transit_lon, cusps)
    facts["exact_orb"] = round(abs(_angular_distance(transit_lon, natal_lon) - target_angle), 2)

    # Окно действия орба для ИМЕННО этой пары планета/аспект — дешёвое
    # посуточное сканирование в обе стороны, не полный calculate_transits().
    orb_limit = TRANSIT_ORBS.get(aspect_type, 2.0)

    def _orb_at(d: date) -> float:
        return abs(_angular_distance(_lon_at(d), natal_lon) - target_angle)

    MAX_SCAN_DAYS = 400
    d = peak_date
    for _ in range(MAX_SCAN_DAYS):
        prev = d - timedelta(days=1)
        if _orb_at(prev) > orb_limit:
            break
        d = prev
    facts["period_start"] = d.isoformat()

    d = peak_date
    for _ in range(MAX_SCAN_DAYS):
        nxt = d + timedelta(days=1)
        if _orb_at(nxt) > orb_limit:
            break
        d = nxt
    facts["period_end"] = d.isoformat()

    return facts


def interpret_event_facts(chart, transit_planet: str, natal_planet: str, aspect_type: str,
                          peak_date: date, tz: str, sky: bool, ev=None) -> tuple[dict | None, str | None]:
    """Факты разбора под флагом sky_event (задание 4.5) — ОДНА функция для
    ручки разбора и прогона согласованности: скрипт сверяет то же, что
    видит человек.

    (факты, ключ события) из ядра; (None, None) — флаг выключен или события у
    ядра нет: тогда вызывающий идёт старым путём (`compute_exact_facts`).
    `ev` — событие уже найдено (чат, 4.6: активные сегодня события ядра)."""
    if not sky:
        return None, None
    from backend.chart_points import cusps
    from backend.sky import find_event, interpret_facts
    ev = ev or find_event(chart, transit_planet, natal_planet, aspect_type, peak_date)
    if ev is None:
        return None, None
    return interpret_facts(ev, tz, cusps(chart)), ev.key


def get_transit_summary(events: list[TransitEvent]) -> dict:
    summary = {
        "total_events":      len(events),
        "by_aspect":         {},
        "by_transit_planet": {},
        "significant":       [],
    }
    for e in events:
        summary["by_aspect"][e.aspect_type]             = summary["by_aspect"].get(e.aspect_type, 0) + 1
        summary["by_transit_planet"][e.transit_planet]  = summary["by_transit_planet"].get(e.transit_planet, 0) + 1

    for e in sorted(events, key=lambda x: x.peak_orb)[:10]:
        summary["significant"].append({
            "date":        e.peak_date,
            "description": f"{e.transit_planet} {e.aspect_type} {e.natal_planet}",
            "orb":         e.peak_orb,
            "exact_date":  e.exact_date,
            "period":      f"{e.start_date} → {e.end_date}",
        })
    return summary


# ═══════════════════════════════════════════════════════════
# TRANSIT ALERT — медленные планеты
# ═══════════════════════════════════════════════════════════

# Плутон — с 05.10.2026 (шаг 5 аудита, решение владельца 02.10.2026): он был
# в main_event, PDF и чате, а «Важный транзит» его не знал.
ALERT_PLANETS  = {"Jupiter", "Saturn", "Uranus", "Neptune", "Pluto"}

# Тон описания задаёт категория аспекта, а не сам транзитный планет.
ASPECT_TONE = {
    "trine": "harmonious", "sextile": "harmonious",
    "square": "tense", "opposition": "tense",
    "conjunction": "new_cycle",
}

# Конкретная сфера жизни для пары (транзитная планета, натальная точка) —
# используется вместе с ASPECT_TONE, чтобы описание было предметным, а не
# общей фразой про "рост и новые возможности".
NATAL_SPHERE = {
    ("Jupiter", "Sun"):        "как тебя видят и слышат — уверенность, право занимать больше места",
    ("Jupiter", "Moon"):       "дом, семья и то, что даёт тебе ощущение опоры",
    ("Jupiter", "Venus"):      "отношения, деньги и всё, что приносит удовольствие",
    ("Jupiter", "Mars"):       "энергия и готовность действовать на опережение",
    ("Jupiter", "Mercury"):    "разговоры, договорённости и то, чему ты сейчас учишься",
    ("Jupiter", "Ascendant"):  "то, как ты подаёшь себя миру",
    ("Jupiter", "Midheaven"):  "карьера и публичная репутация",

    ("Saturn", "Sun"):         "твои границы и то, за что ты берёшься отвечать",
    ("Saturn", "Moon"):        "дом и эмоциональная опора — насколько она устойчива на самом деле",
    ("Saturn", "Venus"):       "отношения и финансы — их сейчас проверяют на прочность",
    ("Saturn", "Mars"):        "выносливость и дисциплина в действиях",
    ("Saturn", "Mercury"):     "важные документы, договоры и решения",
    ("Saturn", "Ascendant"):   "образ себя и груз ответственности, который лежит на тебе",
    ("Saturn", "Midheaven"):   "карьера и долгосрочные цели",

    ("Uranus", "Sun"):         "потребность в свободе и обновлении себя",
    ("Uranus", "Moon"):        "быт и эмоциональные привычки — возможны внезапные перемены дома",
    ("Uranus", "Venus"):       "отношения и финансы — вероятны неожиданные повороты",
    ("Uranus", "Mars"):        "импульсивные решения и резкие вспышки энергии",
    ("Uranus", "Mercury"):     "мышление — неожиданные идеи и новости",
    ("Uranus", "Ascendant"):   "желание радикально изменить свой образ",
    ("Uranus", "Midheaven"):   "карьера — вероятен резкий поворот курса",

    ("Neptune", "Sun"):        "самоощущение и источник вдохновения",
    ("Neptune", "Moon"):       "эмоции и интуиция — чувствительность обострена",
    ("Neptune", "Venus"):      "отношения — риск идеализации и разочарований",
    ("Neptune", "Mars"):       "чёткость целей — важно не распыляться",
    ("Neptune", "Mercury"):    "мышление — интуиция сильнее логики, факты стоит перепроверять",
    ("Neptune", "Ascendant"):  "образ себя — становится мягче и не таким чётким",
    ("Neptune", "Midheaven"):  "карьера — вдохновение важнее рутины, легко потерять ориентиры",

    # Таблицы владельца 05.10.2026 (шаг 5): Плутон и все пары ALERT_PLANETS ×
    # day_event.points — без пропусков, полноту держит
    # test_points_dictionaries.py. ⚠️ Первая часть (до « — ») без запятой:
    # пуш режет сферу по запятой (push/cron._sphere_short).
    ("Pluto", "Sun"):          "сила и право решать за себя",
    ("Pluto", "Moon"):         "чувства и ощущение опоры — меняется то, что казалось незыблемым",
    ("Pluto", "Venus"):        "отношения и деньги — уходит то, что держится по привычке",
    ("Pluto", "Mars"):         "воля и сила действовать",
    ("Pluto", "Mercury"):      "мысли и разговоры — тянет докопаться до сути",
    ("Pluto", "Ascendant"):    "образ себя — меняется глубоко и надолго",
    ("Pluto", "Midheaven"):    "карьера и влияние",

    ("Jupiter", "Jupiter"):    "планы и вера в свои силы — время выбрать, куда расти дальше",
    ("Jupiter", "Saturn"):     "обязанности и правила — появляется опора для долгих дел",
    ("Jupiter", "Uranus"):     "желание свободы и перемен — открываются новые пути",
    ("Jupiter", "Neptune"):    "мечты и воображение — легче поверить в задуманное",
    ("Jupiter", "Pluto"):      "влияние и сила желания — растут возможности что-то изменить",
    ("Jupiter", "North Node"): "направление роста — легче сделать шаг к новому",

    ("Saturn", "Jupiter"):     "планы и надежды — проверка на реальность",
    ("Saturn", "Saturn"):      "жизненные рамки — время подвести итоги и пересобрать планы",
    ("Saturn", "Uranus"):      "свобода и обязанности — поиск равновесия между ними",
    ("Saturn", "Neptune"):     "мечты и иллюзии — время отделить реальное от желаемого",
    ("Saturn", "Pluto"):       "власть и контроль — проверка того, что ты действительно держишь",
    ("Saturn", "North Node"):  "направление роста — нужны терпение и последовательность",

    ("Uranus", "Jupiter"):     "планы и убеждения — возможны неожиданные шансы",
    ("Uranus", "Saturn"):      "привычный порядок — старые правила просят обновления",
    ("Uranus", "Uranus"):      "потребность в свободе — тянет изменить привычный уклад",
    ("Uranus", "Neptune"):     "мечты и идеалы — вдохновение приходит внезапно",
    ("Uranus", "Pluto"):       "глубинные перемены — то, что долго копилось, выходит наружу",
    ("Uranus", "North Node"):  "направление роста — возможен резкий поворот",

    ("Neptune", "Jupiter"):    "вера и планы — легко переоценить возможности",
    ("Neptune", "Saturn"):     "обязанности и границы — они становятся размытыми",
    ("Neptune", "Uranus"):     "перемены и интуиция — важно не терять опору",
    ("Neptune", "Neptune"):    "мечты и вдохновение — время прислушаться к себе",
    ("Neptune", "Pluto"):      "глубокие чувства — тянет к тишине и уединению",
    ("Neptune", "North Node"): "направление роста — ориентиры становятся менее чёткими",

    ("Pluto", "Jupiter"):      "планы и убеждения — меняются взгляды на то, к чему стремиться",
    ("Pluto", "Saturn"):       "обязанности и правила — то, что отслужило, уходит",
    ("Pluto", "Uranus"):       "свобода и перемены — давняя потребность выходит на первый план",
    ("Pluto", "Neptune"):      "мечты и идеалы — что-то из них приходится отпустить",
    ("Pluto", "Pluto"):        "сила и контроль — время пересмотреть, на что ты тратишь силы",
    ("Pluto", "North Node"):   "направление роста — перемены задают новый курс",
}

DESCRIPTION_TEMPLATES = {
    "harmonious": "{planet} сейчас поддерживает тему: {sphere}. Хорошее время сделать конкретный шаг именно здесь — момент работает на тебя.",
    "tense":      "{planet} создаёт напряжение в теме: {sphere}. Это ощущается, но с этим можно работать — вложи усилие именно сюда, и точка напряжения станет опорой.",
    "new_cycle":  "{planet} запускает новый цикл в теме: {sphere}. То, что ты начнёшь сейчас, будет определять эту сферу на годы вперёд.",
}

FALLBACK_DESCRIPTIONS = {
    "harmonious": "Один из благоприятных периодов — {planet} активирует твою карту. Хороший момент сделать конкретный шаг в важной для тебя сфере.",
    "tense":      "{planet} требует осознанности и терпения. Не время торопиться — лучше укрепить то, что для тебя важно, чем начинать новое.",
    "new_cycle":  "{planet} запускает новый цикл в твоей карте. Обрати внимание, что начинается сейчас — это задаст тон на годы вперёд.",
}


def _build_transit_alert_description(transit_planet: str, natal_planet: str, aspect_type: str, planet_ru: str) -> str:
    tone   = ASPECT_TONE.get(aspect_type, "tense")
    sphere = NATAL_SPHERE.get((transit_planet, natal_planet))
    template = DESCRIPTION_TEMPLATES[tone] if sphere else FALLBACK_DESCRIPTIONS[tone]
    return template.format(planet=planet_ru, sphere=sphere)


# Тема письма — без «🌟» (решение владельца 05.10.2026); состояние/тема сначала, потом ход (см. документация/astrea_план_продаж.md,
# раздел 2 «Голос Astrea»). {sphere} — часть NATAL_SPHERE до « — », целиком. ⚠️ Не резать по
# запятой: до 01.10.2026 тема выходила «Сатурн: твои границы и то — …» (сфера «твои границы
# и то, за что ты берёшься отвечать»). Держит test_transit_alert_subject.py.
SUBJECT_TEMPLATES = {
    "harmonious": ("Окно открылось: {sphere} — что сделать · Aristea Timeline",
                   "{planet} открывает благоприятный период — что сделать · Aristea Timeline"),
    "tense":      ("{planet}: {sphere} — как использовать напряжение · Aristea Timeline",
                   "{planet} проверяет на прочность — что делать · Aristea Timeline"),
    "new_cycle":  ("{planet} запускает новый цикл: {sphere} · Aristea Timeline",
                   "{planet} запускает новый цикл в твоей карте · Aristea Timeline"),
}


def _build_transit_alert_subject(transit_planet: str, natal_planet: str, aspect_type: str, planet_ru: str) -> str:
    tone   = ASPECT_TONE.get(aspect_type, "tense")
    sphere = NATAL_SPHERE.get((transit_planet, natal_planet))
    with_sphere, without_sphere = SUBJECT_TEMPLATES[tone]
    if sphere:
        sphere_short = sphere.split(" — ")[0]
        return with_sphere.format(planet=planet_ru, sphere=sphere_short)
    return without_sphere.format(planet=planet_ru)


def alert_event(chart, local_date: date, tzname: str, sky: bool | None = None):
    """Событие письма «Важный транзит» в местные сутки `local_date`: точное
    касание медленной планеты (ALERT_PLANETS) к натальной точке, самое
    сильное по баллу (одна шкала — day_event), или None.

    Кандидаты — те же, что у main_event (day_event._candidates): точки
    day_event.points, к узлам только соединение и оппозиция, момент — точный,
    внутри местных суток. Окно уведомлений здесь не действует: это письмо.
    """
    from zoneinfo import ZoneInfo
    from backend.day_event import _candidates
    try:
        tz = ZoneInfo(tzname)
    except Exception:
        tz = ZoneInfo("Europe/Moscow")
    evs = [e for e in _candidates(chart, local_date, tz, sky) if e.natal and e.transit in ALERT_PLANETS]
    return min(evs, key=lambda e: (-e.score, e.key), default=None)


async def send_transit_alert(to: str, chart_id: str, ev, unsubscribe_url: str) -> bool:
    """Письмо «Важный транзит» про событие `ev` (alert_event).

    ⚠️ До 05.10.2026 письмо уходило только побочным эффектом GET /transits —
    то есть если человек открыл транзиты на вебе (ошибка, решение владельца
    02.10.2026). Теперь его шлёт ежечасный прогон писем
    (lifecycle_emails._send_transit_alerts) в день точного касания.
    """
    from backend.email_service import send_transit_alert_email, APP_URL
    from backend.ephemeris.ru_names import PLANET_RU, ASPECT_RU as ASP_RU

    tp, npl, asp = ev.transit, ev.natal, ev.aspect
    planet_ru = PLANET_RU.get(tp, tp)
    # Дата пика в формате движка — UTC-дата точного момента: event_key
    # совпадает с eventKey() в TransitTimeline.jsx (вкладка «Транзиты»), и
    # страница сама откроет это событие. quote() — "North Node" с пробелом.
    peak_date = ev.at_local.astimezone(timezone.utc).date().isoformat()
    event_key = f"{peak_date}-{tp}-{npl}-{asp}"
    link = f"{APP_URL}/chart/{chart_id}?tab=transits&event={quote(event_key)}" if chart_id else APP_URL
    return await send_transit_alert_email(
        to=to,
        planet=planet_ru,
        aspect=ASP_RU.get(asp, asp),
        natal_planet=PLANET_RU.get(npl, npl),
        date_str=ev.at_local.date().isoformat(),
        description=_build_transit_alert_description(tp, npl, asp, planet_ru),
        subject=_build_transit_alert_subject(tp, npl, asp, planet_ru),
        link=link,
        is_peak=False,
        unsubscribe_url=unsubscribe_url,
    )


# ═══════════════════════════════════════════════════════════
# LUNAR RETURN (задача 2)
# ═══════════════════════════════════════════════════════════

def get_next_lunar_return(natal_chart: dict, from_date: date) -> date:
    """Find the next date when the Moon returns to its natal sign.

    Iterates day-by-day from from_date until the transit Moon sign
    matches the natal Moon sign. Returns that date.
    """
    # Natal Moon sign
    planets = natal_chart.get("planets", [])
    natal_moon_sign = None
    for p in planets:
        if p.get("name") == "Moon":
            natal_moon_sign = p.get("sign")
            break

    if not natal_moon_sign:
        # fallback: возвращаем через 28 дней
        return from_date + timedelta(days=28)

    moon_id = PLANETS["Moon"]
    current = from_date

    for _ in range(60):  # максимум 60 дней поиска (лунный цикл ~28 дней)
        dt = datetime(current.year, current.month, current.day, 12, 0, 0)
        jd = _datetime_to_jd(dt)
        lon, _, _, _ = _calc_planet_position(moon_id, round(jd, 6))
        sign, _ = _longitude_to_sign(lon)
        if sign == natal_moon_sign:
            return current
        current += timedelta(days=1)

    # Не нашли — вернуть через 28 дней
    return from_date + timedelta(days=28)
