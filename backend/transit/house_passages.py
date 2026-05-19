"""Расчёт периодов прохождения транзитных планет по натальным домам.

Точные даты входа/выхода — через шаговое сканирование + бисекция.
Куспиды натальных домов берутся в той же системе, в которой строилась карта.

Используется планировщиком, чтобы не давать ИИ угадывать даты.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

from backend.ephemeris.calculator import (
    PLANETS,
    _calc_planet_position,
    _datetime_to_jd,
    _find_house,
)


# Шаги сканирования по скорости планет
STEP_HOURS = {
    "Moon":    0.5,  # ~13°/сут — шаг 30 мин для точности бисекции
    "Sun":     6,
    "Mercury": 4,    # умеет тормозить и идти ретроградно
    "Venus":   6,
    "Mars":    12,
    "Jupiter": 24,
    "Saturn":  24,
    "Uranus":  24,
    "Neptune": 24,
    "Pluto":   24,
    "North Node": 24,
}

DAY_RU_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
PLANET_NAMES_RU = {
    "Sun":     ("Солнце",   "sun",     "☀️"),
    "Moon":    ("Луна",     "moon",    "🌙"),
    "Mercury": ("Меркурий", "mercury", "⚕️"),
    "Venus":   ("Венера",   "venus",   "♀️"),
    "Mars":    ("Марс",     "mars",    "🔴"),
    "Jupiter": ("Юпитер",   "jupiter", "♃"),
    "Saturn":  ("Сатурн",   "saturn",  "♄"),
    "Uranus":  ("Уран",     "uranus",  "♅"),
    "Neptune": ("Нептун",   "neptune", "♆"),
    "Pluto":   ("Плутон",   "pluto",   "♇"),
}


def _extract_cusps(natal_profile: dict) -> list[float]:
    """Достать 12 куспидов натальных домов как list[float] (эклиптические долготы)."""
    houses = natal_profile.get("houses") or []
    cusps = [0.0] * 12
    for h in houses:
        num = h.get("number") or h.get("num")
        deg = h.get("degree")
        if num is None or deg is None:
            continue
        idx = int(num) - 1
        if 0 <= idx < 12:
            cusps[idx] = float(deg)
    return cusps


def _planet_house_at(planet_id: int, dt: datetime, cusps: list[float]) -> int:
    """Дом транзитной планеты в момент `dt`."""
    jd = _datetime_to_jd(dt)
    lon, _, _, _ = _calc_planet_position(planet_id, round(jd, 6))
    return _find_house(lon, cusps)


def _bisect_house_change(
    planet_id: int,
    cusps: list[float],
    t_before: datetime,
    t_after: datetime,
    house_before: int,
    iterations: int = 20,
) -> datetime:
    """Найти точный момент смены дома между `t_before` (дом=house_before) и `t_after`.

    Возвращает первый момент в новом доме.
    """
    lo, hi = t_before, t_after
    for _ in range(iterations):
        mid = lo + (hi - lo) / 2
        if _planet_house_at(planet_id, mid, cusps) == house_before:
            lo = mid
        else:
            hi = mid
    return hi  # первый момент в новом доме


def calculate_house_passages(
    planet_name: str,
    cusps: list[float],
    from_dt: datetime,
    to_dt: datetime,
    step_hours: Optional[int] = None,
) -> list[dict]:
    """Список периодов нахождения транзитной планеты в каждом доме.

    Каждый период:
        {
          "house":    int (1..12),
          "start_dt": datetime,         # первый момент в этом доме
          "end_dt":   datetime,         # последний момент в этом доме
        }

    Если планета не меняла дом за период — вернётся один элемент.
    """
    if planet_name not in PLANETS:
        return []

    planet_id = PLANETS[planet_name]
    step = step_hours if step_hours is not None else STEP_HOURS.get(planet_name, 24)
    step_td = timedelta(hours=step)

    # Дом в стартовый момент
    current = from_dt
    prev_house = _planet_house_at(planet_id, current, cusps)
    period_start = current

    periods: list[dict] = []
    next_t = current + step_td

    while next_t <= to_dt:
        cur_house = _planet_house_at(planet_id, next_t, cusps)
        if cur_house != prev_house:
            transition = _bisect_house_change(
                planet_id, cusps, current, next_t, prev_house
            )
            periods.append({
                "house":    prev_house,
                "start_dt": period_start,
                "end_dt":   transition - timedelta(minutes=1),
            })
            period_start = transition
            prev_house = cur_house
        current = next_t
        next_t = current + step_td

    # Закрыть последний период
    periods.append({
        "house":    prev_house,
        "start_dt": period_start,
        "end_dt":   to_dt,
    })

    return periods


def _fmt_date_short(dt: datetime) -> str:
    return dt.strftime("%d.%m")


def _fmt_period(start: datetime, end: datetime) -> str:
    return f"{_fmt_date_short(start)} — {_fmt_date_short(end)}"


def compute_planner_periods(
    natal_profile: dict,
    from_date: date,
    to_date: date,
    today: Optional[date] = None,
    user_timezone: Optional[str] = None,
) -> dict:
    """Готовая структура для промпта планера: уже посчитанные периоды по домам.

    Возвращает:
    {
      "fast_planets": [
        {"planet_name": "Солнце", "planet_key": "sun", "emoji": "☀️",
         "periods": [{"period": "01.05 — 17.05", "house": 3}, ...]},
        ...
      ],
      "moon_week": [
        {"date": "19.05 Пн", "house_starts": [
            {"house": 5, "from_time": "00:00"},
            {"house": 6, "from_time": "14:30"},
         ]},
        ...
      ],
      "slow_planets": [
        {"planet_name": "Юпитер", "planet_key": "jupiter", "emoji": "♃",
         "house": 7, "period_label": "01.05 — 31.05"},
        ...
      ],
    }
    """
    if today is None:
        today = date.today()

    cusps = _extract_cusps(natal_profile)

    # Если все куспиды нулевые — натальная карта без времени, периоды считать смысла нет
    if all(c == 0.0 for c in cusps):
        return {"fast_planets": [], "moon_week": [], "slow_planets": []}

    period_start_dt = datetime(from_date.year, from_date.month, from_date.day, 0, 0)
    period_end_dt = datetime(to_date.year, to_date.month, to_date.day, 23, 59)

    # ── Быстрые планеты: Солнце, Меркурий, Венера, Марс — на весь месяц ──
    fast_result = []
    for planet in ("Sun", "Mercury", "Venus", "Mars"):
        passages = calculate_house_passages(planet, cusps, period_start_dt, period_end_dt)
        name_ru, key, emoji = PLANET_NAMES_RU[planet]
        fast_result.append({
            "planet_name": name_ru,
            "planet_key":  key,
            "emoji":       emoji,
            "periods": [
                {
                    "period": _fmt_period(p["start_dt"], p["end_dt"]),
                    "house":  p["house"],
                }
                for p in passages
            ],
        })

    # ── Луна на 7 дней от today ──
    # Сканирование всегда в UTC; сдвиг для отображения считается отдельно
    import pytz
    tz_offset = timedelta(0)
    if user_timezone:
        try:
            tz = pytz.timezone(user_timezone)
            tz_offset = tz.utcoffset(datetime.utcnow())
        except Exception:
            tz_offset = timedelta(0)

    # today в локальном времени пользователя — переводим начало дня в UTC для сканирования
    local_day_start = datetime(today.year, today.month, today.day, 0, 0)
    week_dt_start_utc = local_day_start - tz_offset
    week_dt_end_utc = week_dt_start_utc + timedelta(days=7) - timedelta(minutes=1)
    moon_passages = calculate_house_passages("Moon", cusps, week_dt_start_utc, week_dt_end_utc)

    # Группируем по дням (в локальном времени пользователя)
    moon_week = []
    for i in range(7):
        day_start_local = local_day_start + timedelta(days=i)
        day_end_local = day_start_local + timedelta(days=1) - timedelta(minutes=1)
        day_label = f"{day_start_local.strftime('%d.%m')} {DAY_RU_SHORT[day_start_local.weekday()]}"

        day_start_utc = day_start_local - tz_offset
        day_end_utc = day_end_local - tz_offset

        # Какие куски проходов луны затрагивают этот день?
        day_starts = []
        for p in moon_passages:
            if p["end_dt"] < day_start_utc or p["start_dt"] > day_end_utc:
                continue
            from_time_utc = p["start_dt"] if p["start_dt"] >= day_start_utc else day_start_utc
            to_time_utc   = p["end_dt"]   if p["end_dt"]   <= day_end_utc   else day_end_utc
            from_time_local = from_time_utc + tz_offset
            to_time_local   = to_time_utc   + tz_offset
            day_starts.append({
                "house":      p["house"],
                "from_time":  from_time_local.strftime("%H:%M"),
                "to_time":    to_time_local.strftime("%H:%M"),
                "all_day":    from_time_local.hour == 0 and from_time_local.minute == 0
                              and to_time_local.hour == 23 and to_time_local.minute >= 58,
            })

        # Строим строку времени в Python — не доверяем ИИ форматирование
        if not day_starts:
            time_str = ""
            house_main = 0
        elif len(day_starts) == 1:
            e = day_starts[0]
            if e["from_time"] == "00:00" and e["to_time"] >= "23:58":
                time_str = "весь день"
            elif e["from_time"] == "00:00":
                time_str = f"с 00:00 до {e['to_time']}"
            else:
                time_str = f"с {e['from_time']}"
            house_main = e["house"]
        else:
            parts = []
            for e in day_starts:
                parts.append(f"с {e['from_time']} Луна в {e['house']} доме")
            time_str = ", ".join(parts)
            house_main = day_starts[0]["house"]

        moon_week.append({
            "date":         day_label,
            "time":         time_str,
            "house":        house_main,
            "house_starts": day_starts,
        })

    # ── Медленные планеты: Юпитер..Плутон — берём дом на середину месяца ──
    mid_dt = period_start_dt + (period_end_dt - period_start_dt) / 2
    slow_result = []
    for planet in ("Jupiter", "Saturn", "Uranus", "Neptune", "Pluto"):
        passages = calculate_house_passages(planet, cusps, period_start_dt, period_end_dt)
        name_ru, key, emoji = PLANET_NAMES_RU[planet]
        # Чаще всего медленная планета весь месяц в одном доме — выдадим основной
        main = max(
            passages,
            key=lambda p: (p["end_dt"] - p["start_dt"]).total_seconds(),
            default=None,
        )
        if main is None:
            continue
        slow_result.append({
            "planet_name":  name_ru,
            "planet_key":   key,
            "emoji":        emoji,
            "house":        main["house"],
            "period_label": _fmt_period(main["start_dt"], main["end_dt"]),
        })

    return {
        "fast_planets": fast_result,
        "moon_week":    moon_week,
        "slow_planets": slow_result,
    }
