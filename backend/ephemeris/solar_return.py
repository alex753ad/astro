"""Точный момент солнечного возврата (соляра).

Соляр — карта на момент, когда транзитное Солнце возвращается ровно на
натальную долготу. Расчёт «на день рождения в 12:00» даёт ошибку до суток:
Солнце проходит ~1° в день, так что промах в несколько часов смещает
асцендент соляра на десятки градусов и меняет всю сетку домов.

Схема поиска повторяет `_find_exact_aspect()` из backend/transit/engine.py:
грубое сканирование сеткой, затем тернарный поиск по юлианским дням.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

import swisseph as swe

from backend.ephemeris.aspects import _angular_distance
from backend.ephemeris.calculator import (
    PLANETS,
    _calc_planet_position,
    _datetime_to_jd,
)

logger = logging.getLogger("astro.solar_return")

# Солнце возвращается на ту же долготу раз в году, вблизи даты рождения.
# Окна ±5 суток хватает с запасом на високосные годы и прецессию календаря.
SEARCH_WINDOW_DAYS = 5
COARSE_STEPS = 48          # шаг грубого прохода — ~2.5 часа при окне ±5 суток
TERNARY_ITERATIONS = 40    # точность до секунд


def find_solar_return(natal_sun_longitude: float, natal_dt: datetime, year: int) -> datetime:
    """Момент (UTC), когда Солнце возвращается на натальную долготу в `year`.

    Args:
        natal_sun_longitude: эклиптическая долгота натального Солнца.
        natal_dt: натальный момент в UTC — от него берётся дата рождения.
        year: год, в котором ищется возврат.
    """
    sun_id = PLANETS["Sun"]

    # 29 февраля в невисокосном году — берём 28-е: смещение на сутки
    # компенсируется окном поиска.
    day = natal_dt.day
    if natal_dt.month == 2 and day == 29:
        try:
            datetime(year, 2, 29)
        except ValueError:
            day = 28

    approx = datetime(year, natal_dt.month, day, natal_dt.hour, natal_dt.minute)

    jd_start = _datetime_to_jd(approx - timedelta(days=SEARCH_WINDOW_DAYS))
    jd_end = _datetime_to_jd(approx + timedelta(days=SEARCH_WINDOW_DAYS))

    def orb_at_jd(jd: float) -> float:
        lon, _, _, _ = _calc_planet_position(sun_id, round(jd, 6))
        return _angular_distance(lon, natal_sun_longitude)

    # 1. Грубый проход — находим ячейку с минимальным отклонением.
    best_jd = jd_start
    best_orb = orb_at_jd(jd_start)
    jd_step = (jd_end - jd_start) / COARSE_STEPS

    for i in range(COARSE_STEPS + 1):
        jd = jd_start + i * jd_step
        orb = orb_at_jd(jd)
        if orb < best_orb:
            best_orb = orb
            best_jd = jd

    # 2. Тернарный поиск внутри найденной ячейки.
    lo = best_jd - jd_step
    hi = best_jd + jd_step
    for _ in range(TERNARY_ITERATIONS):
        m1 = lo + (hi - lo) / 3
        m2 = hi - (hi - lo) / 3
        if orb_at_jd(m1) < orb_at_jd(m2):
            hi = m2
        else:
            lo = m1

    jd_exact = (lo + hi) / 2
    y, mo, d, hour_frac = swe.revjul(jd_exact)
    hours = int(hour_frac)
    minutes_frac = (hour_frac - hours) * 60
    minutes = int(minutes_frac)
    seconds = int((minutes_frac - minutes) * 60)

    result = datetime(y, mo, d, hours, minutes, seconds)
    logger.info(
        "Solar return %d: %s (остаточный орб %.6f°)",
        year, result.isoformat(), orb_at_jd(jd_exact),
    )
    return result
