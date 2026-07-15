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

PLANET_SUBTITLES = {
    "Sun":     "Приоритетные сферы месяца",
    "Mercury": "Лучшее время для сбора информации, полезных коммуникаций, наведения порядка и ремонта в темах",
    "Venus":   "Лучшее время для наполнения ресурсом и получения удовольствия через",
    "Mars":    "Лучшее время для проявления активности и инициативности в темах",
    "Jupiter": "Лучшее время для повышения авторитета, расширения, увеличения, привнесения чего-то нового в темах",
    "Saturn":  "Лучшее время для определения зоны ответственности, обретения власти и статуса",
    "Uranus":  "Лучшее время для вливания новых возможностей и мощностей, быстрого развития в темах",
    "Neptune": "Лучшее время чтобы быть осторожным, скрытным в темах",
    "Pluto":   "Лучшее время для осознанной трансформации, разрешения старого ради крутого нового в темах",
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


# Сколько дней сканировать вперёд от конца периода, чтобы найти реальный выход из дома
LOOKAHEAD_DAYS = {
    "Sun":     40,
    "Mercury": 90,
    "Venus":   90,
    "Mars":    100,
    # Медленные планеты: окно должно перекрывать максимально возможное
    # время нахождения в одном доме (иначе дата выхода обрезается по краю окна)
    "Jupiter": 900,     # до ~1.5 года в доме
    "Saturn":  1600,    # до ~4 лет
    "Uranus":  4400,    # до ~12 лет
    "Neptune": 7500,    # до ~20 лет
    "Pluto":   20000,   # до ~55 лет (широкие дома у Плутона)
}

# Сколько дней сканировать назад от начала периода, чтобы найти реальное начало транзита
LOOKBACK_DAYS = {
    "Sun":     40,
    "Mercury": 90,
    "Venus":   90,
    "Mars":    100,
    "Jupiter": 420,
    "Saturn":  1100,
    "Uranus":  3000,
    "Neptune": 5500,
    "Pluto":   8500,
}


def _fmt_date_short(dt: datetime, ref_year: int = None) -> str:
    if ref_year is not None and dt.year != ref_year:
        return dt.strftime("%d.%m.%Y")
    return dt.strftime("%d.%m")


def _fmt_period(start: datetime, end: datetime) -> str:
    return f"{_fmt_date_short(start, end.year)} — {_fmt_date_short(end)}"


# Планеты, способные к ретроградности (без Солнца и Луны)
RETRO_PLANETS = ("Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto")


def _speed_at(planet_id: int, dt: datetime) -> float:
    _, _, _, speed = _calc_planet_position(planet_id, _datetime_to_jd(dt))
    return speed


def compute_retrograde_stations(from_date: date, to_date: date) -> list[dict]:
    """Станции ретроградности (смена направления) внутри отображаемого месяца.

    Возвращает элементы, совместимые с PlannerPage.buildTimeline:
    {"date": "dd.mm", "status": "start"|"end", "planet_name": ..., "label": ...}
    status="start" — планета поворачивает в ретро (директ→ретро),
    status="end"   — возвращается к директному движению (ретро→директ).
    """
    start_dt = datetime(from_date.year, from_date.month, from_date.day, 0, 0)
    end_dt = datetime(to_date.year, to_date.month, to_date.day, 23, 59)
    result: list[dict] = []
    for planet in RETRO_PLANETS:
        pid = PLANETS.get(planet)
        if pid is None:
            continue
        name_ru, key, _emoji = PLANET_NAMES_RU[planet]
        dt = start_dt
        prev_speed = _speed_at(pid, dt)
        step = timedelta(days=1)
        while dt < end_dt:
            nxt = min(dt + step, end_dt)
            speed = _speed_at(pid, nxt)
            if prev_speed == 0:
                prev_speed = speed
            elif (prev_speed < 0) != (speed < 0):
                # смена знака скорости — уточняем момент станции бисекцией
                lo, hi = dt, nxt
                for _ in range(20):
                    mid = lo + (hi - lo) / 2
                    if (_speed_at(pid, mid) < 0) == (prev_speed < 0):
                        lo = mid
                    else:
                        hi = mid
                going_retro = speed < 0  # директ→ретро
                result.append({
                    "date": hi.strftime("%d.%m"),
                    "status": "start" if going_retro else "end",
                    "planet": key,
                    "planet_name": name_ru,
                    "label": f"{'Начало' if going_retro else 'Окончание'} ретро {name_ru}",
                })
            prev_speed = speed
            dt = nxt
    return result


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
    # Полдень текущего дня — для пометки «текущего» периода (E1: Free-витрина планера)
    today_dt = datetime(today.year, today.month, today.day, 12, 0)

    # ── Быстрые планеты: Солнце, Меркурий, Венера, Марс — на весь месяц ──
    fast_result = []
    for planet in ("Sun", "Mercury", "Venus", "Mars"):
        lookback = timedelta(days=LOOKBACK_DAYS.get(planet, 60))
        lookahead = timedelta(days=LOOKAHEAD_DAYS.get(planet, 40))
        all_passages = calculate_house_passages(planet, cusps, period_start_dt - lookback, period_end_dt + lookahead)
        # Оставляем только периоды, пересекающиеся с отображаемым месяцем:
        # заканчиваются не раньше начала месяца И начинаются не позже конца месяца
        passages = [
            p for p in all_passages
            if p["end_dt"] >= period_start_dt and p["start_dt"] <= period_end_dt
        ]
        name_ru, key, emoji = PLANET_NAMES_RU[planet]
        fast_result.append({
            "planet_name":    name_ru,
            "planet_key":     key,
            "emoji":          emoji,
            "planet_subtitle": PLANET_SUBTITLES.get(planet, ""),
            "periods": [
                {
                    "period": _fmt_period(p["start_dt"], p["end_dt"]),
                    "house":  p["house"],
                    "is_current": p["start_dt"] <= today_dt <= p["end_dt"],
                }
                for p in passages
            ],
        })

    # ── Луна на 14 дней от today (периоды нахождения по домам) ──
    import logging as _logging
    _logging.getLogger('astro.house_passages').info('CUSPS: %s', cusps)
    # Сканирование в UTC; сдвиг для отображения применяется к каждому периоду
    import pytz
    tz_offset = timedelta(0)
    if user_timezone:
        try:
            tz = pytz.timezone(user_timezone)
            # FIX: используем дату начала сканирования, а не utcnow(),
            # чтобы корректно учитывать переход на летнее/зимнее время
            local_day_start_probe = datetime(today.year, today.month, today.day, 0, 0)
            tz_offset = tz.utcoffset(local_day_start_probe)
        except Exception:
            tz_offset = timedelta(0)

    # today в локальном времени пользователя — переводим начало дня в UTC для сканирования
    local_day_start = datetime(today.year, today.month, today.day, 0, 0)
    # Начинаем на 3 дня раньше today — чтобы захватить текущий период Луны
    # (Луна меняет дом каждые ~2.5 дня, период мог начаться до сегодня)
    week_dt_start_utc = local_day_start - tz_offset - timedelta(days=3)
    week_dt_end_utc = week_dt_start_utc + timedelta(days=17) - timedelta(minutes=1)
    moon_passages_raw = calculate_house_passages("Moon", cusps, week_dt_start_utc, week_dt_end_utc)

    # FIX: возвращаем периоды нахождения Луны по домам (не группируем по дням).
    # Каждый элемент — один непрерывный период в одном доме со временем входа и выхода.
    moon_week = []
    for p in moon_passages_raw:
        start_local = p["start_dt"] + tz_offset
        end_local   = p["end_dt"]   + tz_offset

        # Метка входа: "21.05 Чт 03:22"
        start_label = (
            f"{start_local.strftime('%d.%m')} "
            f"{DAY_RU_SHORT[start_local.weekday()]} "
            f"{start_local.strftime('%H:%M')}"
        )
        # Метка выхода: "25.05 Пн 01:03"
        end_label = (
            f"{end_local.strftime('%d.%m')} "
            f"{DAY_RU_SHORT[end_local.weekday()]} "
            f"{end_local.strftime('%H:%M')}"
        )

        moon_week.append({
            # date = момент входа Луны в дом (для совместимости с planner_engine)
            "date":  start_label,
            # time = метка "до <дата выхода>" — используется в planner_engine как подзаголовок
            "time":  f"до {end_label}",
            "house": p["house"],
            # Сохраняем полные datetime для возможной дальнейшей обработки
            "start_dt": start_local.isoformat(),
            "end_dt":   end_local.isoformat(),
        })

    # ── Медленные планеты: Юпитер..Плутон — берём дом на середину месяца ──
    slow_result = []
    for planet in ("Jupiter", "Saturn", "Uranus", "Neptune", "Pluto"):
        lookback = timedelta(days=LOOKBACK_DAYS.get(planet, 400))
        lookahead = timedelta(days=LOOKAHEAD_DAYS.get(planet, 400))
        all_passages = calculate_house_passages(
            planet, cusps, period_start_dt - lookback, period_end_dt + lookahead,
            step_hours=72,
        )
        # текущий/действующий период: пересекается с месяцем (начался не позже конца месяца)
        passages = [
            p for p in all_passages
            if p["end_dt"] >= period_start_dt and p["start_dt"] <= period_end_dt
        ]
        name_ru, key, emoji = PLANET_NAMES_RU[planet]
        main = max(
            passages,
            key=lambda p: (p["end_dt"] - p["start_dt"]).total_seconds(),
            default=None,
        )
        if main is None:
            continue
        slow_result.append({
            "planet_name":     name_ru,
            "planet_key":      key,
            "emoji":           emoji,
            "house":           main["house"],
            "period_label":    f'{main["start_dt"].strftime("%d.%m.%Y")} — {main["end_dt"].strftime("%d.%m.%Y")}',
            "planet_subtitle": PLANET_SUBTITLES.get(planet, ""),
        })

    return {
        "fast_planets": fast_result,
        "moon_week":    moon_week,
        "slow_planets": slow_result,
        "retrogrades":  compute_retrograde_stations(from_date, to_date),
    }
