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


def _find_real_entry(
    planet_id: int,
    cusps: list[float],
    boundary_dt: datetime,
    boundary_house: int,
    step_td: timedelta,
    max_steps: int = 4000,
) -> datetime:
    """Реальный момент входа в `boundary_house`, отсканировав НАЗАД от `boundary_dt`
    (который уже находится в этом доме) до смены дома, с уточнением бисекцией.
    """
    anchor = boundary_dt
    for _ in range(max_steps):
        probe = anchor - step_td
        h = _planet_house_at(planet_id, probe, cusps)
        if h != boundary_house:
            return _bisect_house_change(planet_id, cusps, probe, anchor, h)
        anchor = probe
    return boundary_dt  # не нашли смену дома в пределах max_steps — оставляем как есть


def _find_real_exit(
    planet_id: int,
    cusps: list[float],
    boundary_dt: datetime,
    boundary_house: int,
    step_td: timedelta,
    max_steps: int = 4000,
) -> datetime:
    """Реальный момент выхода из `boundary_house`, отсканировав ВПЕРЁД от `boundary_dt`
    (который ещё в этом доме) до смены дома, с уточнением бисекцией.
    """
    anchor = boundary_dt
    for _ in range(max_steps):
        probe = anchor + step_td
        h = _planet_house_at(planet_id, probe, cusps)
        if h != boundary_house:
            return _bisect_house_change(planet_id, cusps, anchor, probe, boundary_house)
        anchor = probe
    return boundary_dt  # не нашли смену дома в пределах max_steps — оставляем как есть


def calculate_house_passages(
    planet_name: str,
    cusps: list[float],
    from_dt: datetime,
    to_dt: datetime,
    step_hours: Optional[int] = None,
    refine_edges: bool = False,
) -> list[dict]:
    """Список периодов нахождения транзитной планеты в каждом доме.

    Каждый период:
        {
          "house":    int (1..12),
          "start_dt": datetime,         # первый момент в этом доме
          "end_dt":   datetime,         # последний момент в этом доме
        }

    Если планета не меняла дом за период — вернётся один элемент.

    `refine_edges=True` — первый и последний период получают РЕАЛЬНЫЙ момент
    входа/выхода (сканированием за пределы [from_dt, to_dt]), а не край окна
    сканирования. По умолчанию выключено: у существующих вызовов (fast/slow
    планеты) уже есть большой запас lookback/lookahead, и лишнее сканирование
    вовне только тратит время впустую.
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

    if refine_edges:
        first = periods[0]
        first["start_dt"] = _find_real_entry(planet_id, cusps, first["start_dt"], first["house"], step_td)

        last = periods[-1]
        exit_dt = _find_real_exit(planet_id, cusps, last["end_dt"], last["house"], step_td)
        last["end_dt"] = exit_dt - timedelta(minutes=1)

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
    week_offset: Optional[int] = None,
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
        # заканчиваются не раньше начала месяца И начинаются не позже конца месяца.
        # Если смотрим текущий/будущий месяц (period_end_dt >= today) — дополнительно
        # прячем период, который уже полностью завершился к сегодняшнему дню (иначе
        # карточка показывает истёкшую дату вместо актуального дома). При просмотре
        # прошлого месяца (Pro-навигация назад) это ограничение не действует.
        hide_fully_past = period_end_dt >= today_dt
        passages = [
            p for p in all_passages
            if p["end_dt"] >= period_start_dt and p["start_dt"] <= period_end_dt
            and (not hide_fully_past or p["end_dt"] >= today_dt)
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
                    # Настоящие границы периода. `period` выше — строка для
                    # показа человеку, и у неё нет года («07.08 — 06.09»):
                    # достать из неё дату можно только парсером, доставая год
                    # откуда-то ещё. Лента (backend/feed/) берёт границы
                    # отсюда, а не разбирает строку обратно. У moon_week ниже
                    # эти два ключа лежат с самого начала — здесь просто то же
                    # самое, симметрично.
                    #
                    # build_planner() собирает свой ответ по именованным полям
                    # и лишние ключи игнорирует — /planner/monthly от их
                    # появления не меняется ни на байт.
                    "start_dt": p["start_dt"].isoformat(),
                    "end_dt":   p["end_dt"].isoformat(),
                }
                for p in passages
            ],
        })

    # ── Луна на текущую календарную неделю (периоды нахождения по домам) ──
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

    # Неделя считается от первой недели ОТОБРАЖАЕМОГО месяца (from_date..to_date),
    # а не от "сегодня" — иначе прокрутка недель (week_offset) не имела бы смысла:
    # чем бы её ни листали, всегда показывалась бы неделя с сегодняшним днём.
    # week_offset=0 — неделя, содержащая первое число месяца (может начинаться
    # в предыдущем месяце, если 1-е — не понедельник); последняя неделя месяца —
    # аналогично может залезать в следующий. Обе показываются целиком.
    month_first_monday = from_date - timedelta(days=from_date.weekday())
    month_last_monday  = to_date - timedelta(days=to_date.weekday())
    total_weeks = (month_last_monday - month_first_monday).days // 7 + 1

    if week_offset is None:
        # Явный сдвиг не задан (первая загрузка месяца) — показываем неделю,
        # содержащую today, если today вообще попадает в этот месяц.
        if from_date <= today <= to_date:
            today_monday = today - timedelta(days=today.weekday())
            resolved_week_offset = (today_monday - month_first_monday).days // 7
        else:
            resolved_week_offset = 0
    else:
        resolved_week_offset = week_offset
    # Границы жёсткие — прокрутка не выходит за пределы месяца (см. ТЗ п.3).
    resolved_week_offset = max(0, min(resolved_week_offset, total_weeks - 1))

    week_start_local = datetime.combine(
        month_first_monday + timedelta(weeks=resolved_week_offset), datetime.min.time(),
    )
    week_end_local = week_start_local + timedelta(days=7) - timedelta(minutes=1)

    # Окно сканирования шире недели (Луна меняет дом раз в ~2.5 дня) — так
    # calculate_house_passages(refine_edges=True) сможет найти реальные
    # момент входа/выхода для периодов, пересекающих границы недели, а не
    # обрежет их по краю окна.
    week_dt_start_utc = week_start_local - tz_offset - timedelta(days=5)
    week_dt_end_utc   = week_end_local   - tz_offset + timedelta(days=5)
    moon_passages_raw = calculate_house_passages(
        "Moon", cusps, week_dt_start_utc, week_dt_end_utc, refine_edges=True,
    )

    # FIX: возвращаем периоды нахождения Луны по домам (не группируем по дням).
    # Каждый элемент — один непрерывный период в одном доме со временем входа и выхода.
    # Оставляем только периоды, ПЕРЕСЕКАЮЩИЕСЯ с текущей неделей (а не только те,
    # что начались внутри неё) — иначе период, начавшийся до понедельника или
    # заканчивающийся после воскресенья, будет потерян или обрезан.
    moon_week = []
    for p in moon_passages_raw:
        start_local = p["start_dt"] + tz_offset
        end_local   = p["end_dt"]   + tz_offset
        if end_local < week_start_local or start_local > week_end_local:
            continue

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
            # time = метка даты выхода — фронт склеивает "date – time" через тире
            "time":  end_label,
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
        # Берём период, который реально содержит "сегодня" — раньше здесь ошибочно
        # выбирался самый длинный по продолжительности из пересекающихся с месяцем,
        # из-за чего при переходе в более короткий (по времени пребывания) дом
        # оставался старый, уже завершившийся период (баг с истёкшими датами).
        main = next((p for p in passages if p["start_dt"] <= today_dt <= p["end_dt"]), None)
        if main is None:
            # today вне пересекающихся периодов (например, просмотр прошлого месяца) —
            # берём последний начавшийся к этому моменту, иначе ближайший будущий.
            started = [p for p in passages if p["start_dt"] <= today_dt]
            main = max(started, key=lambda p: p["start_dt"], default=None)
            if main is None and passages:
                main = min(passages, key=lambda p: p["start_dt"])
        if main is None:
            continue
        slow_result.append({
            "planet_name":     name_ru,
            "planet_key":      key,
            "emoji":           emoji,
            "house":           main["house"],
            "period_label":    f'{main["start_dt"].strftime("%d.%m.%Y")} — {main["end_dt"].strftime("%d.%m.%Y")}',
            "planet_subtitle": PLANET_SUBTITLES.get(planet, ""),
            # См. комментарий у fast_planets выше — настоящие границы для ленты.
            "start_dt": main["start_dt"].isoformat(),
            "end_dt":   main["end_dt"].isoformat(),
        })

    return {
        "fast_planets": fast_result,
        "moon_week":    moon_week,
        "slow_planets": slow_result,
        "retrogrades":  compute_retrograde_stations(from_date, to_date),
        "week_nav": {
            "week_offset": resolved_week_offset,
            "total_weeks": total_weeks,
            "week_start":  week_start_local.date().isoformat(),
            "week_end":    week_end_local.date().isoformat(),
        },
    }
