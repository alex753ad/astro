"""Расчёт периодов прохождения транзитных планет по натальным домам.

Точные даты входа/выхода — через шаговое сканирование + бисекция.
Куспиды натальных домов берутся в той же системе, в которой строилась карта.

Используется планировщиком, чтобы не давать ИИ угадывать даты.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Optional

from backend.ephemeris.calculator import (
    PLANETS,
    _calc_planet_position,
    _datetime_to_jd,
    _find_house,
)
from backend.time_utils import local_day, utc_naive_to_local, valid_timezone


# ── Пояс ──────────────────────────────────────────────────────────────────────
# Движок сканирует в НАИВНОМ UTC. Всё, что видит человек (строки «07.08 —
# 06.09», даты станций и «Ближайших 30 дней»), — местное время его пояса
# (time_utils.user_tz). До 04.10.2026 строки печатались прямо из UTC: период,
# начавшийся в 22:30 UTC, в Москве начинался «вчера» по планеру и «сегодня»
# по ленте (шаг 2 аудита). Пояс не пришёл — UTC, как раньше.

def _zone(user_timezone: Optional[str]) -> str:
    return valid_timezone(user_timezone) or "UTC"


def _day_start_utc(d: date, tz: str) -> datetime:
    """Местная полночь `d` → наивный UTC (вид, в котором считает движок)."""
    return local_day(d, tz)[0].replace(tzinfo=None)


def _local(naive_utc: datetime, tz: str) -> datetime:
    """Наивный UTC движка → наивное местное, только для показа."""
    return utc_naive_to_local(naive_utc, tz).replace(tzinfo=None)


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

# Те же строки, что meta.lead в methodology.json (планер) — лента и планер
# показывают один заголовок планеты. До 29.09.2026 здесь стояли обрывы
# «…в темах», «…получения удовольствия через» (docs/planner_texts_review.md).
PLANET_SUBTITLES = {
    "Sun":     "Приоритетные сферы месяца",
    "Mercury": "Время собирать информацию, договариваться и наводить порядок — в сфере, которую он сейчас проходит",
    "Venus":   "Время для удовольствия, красоты и выгодных решений — в сфере, которую она сейчас проходит",
    "Mars":    "Время действовать первым и начинать — в сфере, которую он сейчас проходит",
    "Jupiter": "Время расти и пробовать новое — в сфере, которую он сейчас проходит",
    "Saturn":  "Лучшее время для определения зоны ответственности, обретения власти и статуса",
    "Uranus":  "Время перемен и неожиданных возможностей — в сфере, которую он сейчас проходит",
    "Neptune": "Время не спешить с выводами и беречь личное — в сфере, которую он сейчас проходит",
    "Pluto":   "Время отпустить отжившее и собрать новое — в сфере, которую он сейчас проходит",
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


# ── Настоящие границы периода ────────────────────────────────────────────────
# Шаг 2б аудита (04.10.2026). До него периоды планет искались в окне «месяц ±
# LOOKBACK/LOOKAHEAD» и у крайних проходов границей становился КРАЙ окна: у
# Солнца в широком доме (дольше 40 дней) планер показывал конец 10.12, лента —
# 14.12, оба выдуманы (окна разные). Теперь крайний проход досчитывается до
# настоящего входа и выхода, а ретроградная петля «H → X → H» — один период H
# до окончательного выхода (решение владельца).

# Сколько дней планета может пробыть вне дома и вернуться в него ретроградной
# петлёй. Вернуться в тот же дом раньше, чем обойдя круг, планета может ТОЛЬКО
# попятным ходом, поэтому повторный вход в пределах этого срока — петля, а не
# новый период. Оценка сверху: дуга ретроградности, пройденная вперёд до
# станции, плюс сама ретроградность (Меркурий ~45 дней, Венера ~75, Марс ~115,
# медленные до ~300). Меньше круга по зодиаку с запасом (Меркурий и Венера
# обходят его за год, Марс — за два). У Солнца петель нет.
LOOP_DAYS = {
    "Mercury": 60, "Venus": 90, "Mars": 150,
    "Jupiter": 360, "Saturn": 360, "Uranus": 360, "Neptune": 360, "Pluto": 360,
}

# Шаг поиска настоящей границы за краем окна, часы. Крупный у медленных:
# Плутон бывает в одном доме десятилетиями. Точность даёт бисекция, а петлю,
# которую крупный шаг перепрыгнет, ловит проверка _seen_within.
EDGE_STEP_HOURS = {"Jupiter": 240, "Saturn": 240, "Uranus": 240, "Neptune": 240, "Pluto": 240}
EDGE_MAX_STEPS = 10000   # 10 суток × 10000 ≈ 270 лет — края не бывает


def _seen_within(planet_id: int, cusps: list[float], t: datetime, house: int,
                 span: timedelta) -> Optional[datetime]:
    """Момент, когда планета была в `house` в пределах `span` от `t` (span < 0
    — назад), иначе None. Шаг — сутки: петля короче суток не бывает."""
    step = timedelta(days=1) if span > timedelta(0) else -timedelta(days=1)
    probe, end = t + step, t + span
    while (probe <= end) if span > timedelta(0) else (probe >= end):
        if _planet_house_at(planet_id, probe, cusps) == house:
            return probe
        probe += step
    return None


def _first_entry(planet: str, cusps: list[float], t: datetime, house: int) -> datetime:
    """Начало периода `house`, в котором планета находится в `t`: первый вход
    с учётом ретроградных петель."""
    pid = PLANETS[planet]
    step = timedelta(hours=EDGE_STEP_HOURS.get(planet, STEP_HOURS.get(planet, 24)))
    loop = timedelta(days=LOOP_DAYS.get(planet, 0))
    while True:
        entry = _find_real_entry(pid, cusps, t, house, step, EDGE_MAX_STEPS)
        earlier = _seen_within(pid, cusps, entry, house, -loop) if loop else None
        if earlier is None:
            return entry
        t = earlier


def _final_exit(planet: str, cusps: list[float], t: datetime, house: int) -> datetime:
    """Первый момент ПОСЛЕ окончательного выхода из `house` (планета в нём в `t`)."""
    pid = PLANETS[planet]
    step = timedelta(hours=EDGE_STEP_HOURS.get(planet, STEP_HOURS.get(planet, 24)))
    loop = timedelta(days=LOOP_DAYS.get(planet, 0))
    while True:
        exit_dt = _find_real_exit(pid, cusps, t, house, step, EDGE_MAX_STEPS)
        later = _seen_within(pid, cusps, exit_dt, house, loop) if loop else None
        if later is None:
            return exit_dt
        t = later


def _merge_loops(periods: list[dict]) -> list[dict]:
    """«H → X → H» — один период H от первого входа до последнего выхода.

    Вернуться в дом через ОДИН соседний планета может только развернувшись,
    поэтому порогов здесь нет. Петля перекрывает соседний период (X тоже
    тянется до своего окончательного выхода) — это верно: планета в эти
    месяцы ходит туда-обратно через куспид.
    """
    out, used = [], set()
    for i, p in enumerate(periods):
        if i in used:
            continue
        j = i
        while j + 2 < len(periods) and periods[j + 2]["house"] == p["house"]:
            j += 2
            used.add(j)
        out.append({"house": p["house"], "start_dt": p["start_dt"], "end_dt": periods[j]["end_dt"]})
    return out


def house_periods(planet: str, cusps: list[float], from_dt: datetime, to_dt: datetime,
                  step_hours: Optional[int] = None) -> list[dict]:
    """Периоды планеты по домам, пересекающие [from_dt, to_dt], с НАСТОЯЩИМИ
    границами: первый вход и окончательный выход, петли склеены.

    Окно сканирования шире запрошенного на две петли: петля, перерезанная
    краем, оказывается внутри целиком. Досчитывается только проход, упёршийся
    в край сканирования (`start_dt == scan_from`, `end_dt == scan_to`), —
    остальные границы уже настоящие (бисекция).
    """
    loop = timedelta(days=LOOP_DAYS.get(planet, 0))
    scan_from, scan_to = from_dt - 2 * loop, to_dt + 2 * loop
    raw = calculate_house_passages(planet, cusps, scan_from, scan_to, step_hours=step_hours)
    if not raw:
        return []
    if raw[0]["start_dt"] == scan_from:
        raw[0]["start_dt"] = _first_entry(planet, cusps, scan_from, raw[0]["house"])
    if raw[-1]["end_dt"] == scan_to:
        raw[-1]["end_dt"] = _final_exit(planet, cusps, scan_to, raw[-1]["house"]) - timedelta(minutes=1)
    return [p for p in _merge_loops(raw) if p["end_dt"] >= from_dt and p["start_dt"] <= to_dt]


def period_starts(planet: str, cusps: list[float], from_dt: datetime, to_dt: datetime,
                  step_hours: Optional[int] = None) -> list[dict]:
    """Начала НОВЫХ периодов в [from_dt, to_dt]: вход в дом, кроме возврата
    ретроградной петлёй. Дёшево — без досчёта краёв (пуши, «Ближайшие 30
    дней»): нужны только входы внутри окна. → [{"house", "start_dt"}]."""
    pid = PLANETS[planet]
    loop = timedelta(days=LOOP_DAYS.get(planet, 0))
    out = []
    for p in calculate_house_passages(planet, cusps, from_dt, to_dt, step_hours=step_hours)[1:]:
        if loop and _seen_within(pid, cusps, p["start_dt"], p["house"], -loop):
            continue  # возврат петлёй — продолжение прежнего периода
        out.append({"house": p["house"], "start_dt": p["start_dt"]})
    return out


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


def compute_retrograde_stations(from_date: date, to_date: date,
                                user_timezone: Optional[str] = None) -> list[dict]:
    """Станции ретроградности (смена направления) в местных сутках
    [from_date, to_date] пояса `user_timezone`.

    Возвращает элементы, совместимые с PlannerPage.buildTimeline:
    {"date": "dd.mm", "status": "start"|"end", "planet_name": ..., "label": ...}
    status="start" — планета поворачивает в ретро (директ→ретро),
    status="end"   — возвращается к директному движению (ретро→директ).
    `date`/`date_iso` — МЕСТНАЯ дата, `at` — точный момент (aware UTC, ISO).
    ⚠️ До 04.10.2026 дата была UTC, а лента ставила станцию на 12:00 UTC:
    станция в 23:00 по Москве уезжала на соседние сутки.
    """
    tz = _zone(user_timezone)
    start_dt = _day_start_utc(from_date, tz)
    end_dt = _day_start_utc(to_date + timedelta(days=1), tz) - timedelta(minutes=1)
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
                local = _local(hi, tz)
                result.append({
                    "date": local.strftime("%d.%m"),
                    # С годом — для «Ближайших 30 дней» (compute_upcoming),
                    # окно которых переходит через границу месяца и года.
                    "date_iso": local.date().isoformat(),
                    "at": hi.replace(tzinfo=timezone.utc, microsecond=0).isoformat(),
                    "status": "start" if going_retro else "end",
                    "planet": key,
                    "planet_name": name_ru,
                    # ⚠️ «Уран: начало ретроградности», а не «Начало ретро Уран».
                    # Прежняя формулировка была не по-русски: имя планеты стояло
                    # в именительном падеже там, где нужен родительный
                    # («начало ретроградности Урана»).
                    #
                    # Родительный падеж НЕ вводится намеренно: словаря склонений
                    # планет на бэкенде нет, а заводить его пришлось бы третьим
                    # местом склонений в проекте (есть _plural в письмах и
                    # ruDeclension.js на фронте — см. CLAUDE.md). Двоеточие
                    # снимает вопрос целиком: подлежащее в именительном, дальше
                    # подпись. Тот же приём, что у меток групп в планере.
                    "label": f"{name_ru}: {'начало' if going_retro else 'конец'} ретроградности",
                })
            prev_speed = speed
            dt = nxt
    return result


UPCOMING_DAYS = 30


def compute_upcoming(natal_profile: dict, today: date, days: int = UPCOMING_DAYS,
                     user_timezone: Optional[str] = None) -> list[dict]:
    """«Ближайшие 30 дней» в планере: переходы планет (Солнце–Плутон) в
    следующий дом и развороты (станции) — скользящее окно от `today`, не
    отображаемый месяц (решение владельца 29.09.2026).

    Фазы Луны сюда не входят: клиент берёт их из /calendar/lunar, открытой
    всем, — второй расчёт фаз дал бы вторую сетку поясов (см. get_eclipses).

    От тарифа не зависит: дата перехода и номер дома видны и на бесплатном
    (текст периода закрыт отдельно, в build_planner).

    Элементы: {"date": "ГГГГ-ММ-ДД", "kind": "passage"|"station",
    "planet", "planet_name", "house", "until"} у перехода и
    {..., "status": "start"|"end"} у станции.
    """
    cusps = _extract_cusps(natal_profile)
    if all(c == 0.0 for c in cusps):
        return []
    tz = _zone(user_timezone)
    start = _day_start_utc(today, tz)
    end = _day_start_utc(today + timedelta(days=days + 1), tz) - timedelta(minutes=1)
    out: list[dict] = []
    for planet in ("Sun", "Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto"):
        slow = planet in ("Jupiter", "Saturn", "Uranus", "Neptune", "Pluto")
        name_ru, key, _emoji = PLANET_NAMES_RU[planet]
        # Только НОВЫЕ периоды: край окна — не вход, возврат петлёй — тоже.
        # «До» — окончательный выход (шаг 2б), а не выход до петли.
        for p in period_starts(planet, cusps, start, end, step_hours=72 if slow else None):
            until = _final_exit(planet, cusps, p["start_dt"], p["house"]) - timedelta(minutes=1)
            out.append({
                "date": _local(p["start_dt"], tz).date().isoformat(),
                "kind": "passage",
                "planet": key,
                "planet_name": name_ru,
                "house": p["house"],
                "until": _local(until, tz).date().isoformat(),
            })
    for r in compute_retrograde_stations(today, today + timedelta(days=days), tz):
        out.append({
            "date": r["date_iso"], "kind": "station", "planet": r["planet"],
            "planet_name": r["planet_name"], "status": r["status"],
        })
    out.sort(key=lambda e: e["date"])
    return out


# Запас сканирования по обе стороны окна, в сутках.
#
# Луна меняет дом раз в ~2.3 суток, и запас нужен НЕ ради точности расчёта,
# а ради границ выдачи: без него первый и последний период обрезались бы краем
# окна сканирования и приезжали бы с временем ровно 00:00 — выдуманным
# моментом, который выглядит как настоящий вход в дом. Пять суток покрывают
# самый длинный проход Луны по широкому дому с запасом.
MOON_SCAN_PAD_DAYS = 5


def moon_tz_offset(user_timezone: Optional[str], probe_day: date) -> timedelta:
    """Смещение пояса пользователя на конкретный день.

    Сканирование идёт в UTC, а показываем местное время — сдвиг применяется к
    каждому периоду. Берётся на ДЕНЬ НАЧАЛА окна, а не на «сейчас»: иначе окно,
    пересекающее переход на летнее время, сдвинулось бы целиком по последнему
    состоянию часов.
    """
    if not user_timezone:
        return timedelta(0)
    try:
        import pytz
        tz = pytz.timezone(user_timezone)
        return tz.utcoffset(datetime(probe_day.year, probe_day.month, probe_day.day, 0, 0))
    except Exception:
        return timedelta(0)


def _moon_passages_between(
    cusps: list[float],
    win_start_local: datetime,
    win_end_local: datetime,
    tz_offset: timedelta,
) -> list[dict]:
    """Проходы Луны по домам, ПЕРЕСЕКАЮЩИЕ окно [win_start_local, win_end_local].

    Одна реализация на оба потребителя: недельную вкладку веб-планера
    (compute_planner_periods ниже) и ленту (compute_moon_house_passages).
    Вторая копия разъехалась бы с первой при первой же правке формата меток —
    а метки веб-планер разбирает глазами человека, то есть расхождение было бы
    видно только на скриншоте.

    ⚠️ Граница окна проходит ПО ПРОХОДАМ, а не по полуночи. Оставляем период,
    который окно пересекает, целиком и с его настоящими временами: проход,
    начавшийся в субботу до окна или кончающийся во вторник после него, —
    это один проход, а не два. Обрезка по краю дала бы «дата 00:00» —
    момент, которого не было.
    """
    scan_from = win_start_local - tz_offset - timedelta(days=MOON_SCAN_PAD_DAYS)
    scan_to   = win_end_local   - tz_offset + timedelta(days=MOON_SCAN_PAD_DAYS)
    raw = calculate_house_passages("Moon", cusps, scan_from, scan_to, refine_edges=True)

    result = []
    for p in raw:
        start_local = p["start_dt"] + tz_offset
        end_local   = p["end_dt"]   + tz_offset
        if end_local < win_start_local or start_local > win_end_local:
            continue
        result.append({
            # date = момент входа Луны в дом: "21.05 Чт 03:22".
            # ⚠️ Имя вводит в заблуждение и оставлено ради совместимости с
            # planner_engine и PlannerPage.jsx: внутри и дата, и время.
            "date":  _moon_label(start_local),
            # time = момент выхода, тем же форматом. Фронт склеивает их тире.
            "time":  _moon_label(end_local),
            "house": p["house"],
            # Настоящие границы для ленты — она строку не разбирает.
            "start_dt": start_local.isoformat(),
            "end_dt":   end_local.isoformat(),
        })
    return result


def _moon_label(dt_local: datetime) -> str:
    return f"{dt_local.strftime('%d.%m')} {DAY_RU_SHORT[dt_local.weekday()]} {dt_local.strftime('%H:%M')}"


def compute_moon_house_passages(
    natal_profile: dict,
    from_date: date,
    to_date: date,
    user_timezone: Optional[str] = None,
) -> list[dict]:
    """Проходы Луны по домам за ПРОИЗВОЛЬНОЕ окно — режим ленты.

    ⚠️ Зачем отдельная функция, а не параметр у compute_planner_periods.
    Недельная вкладка веб-планера листается (`week_offset`), и её неделя
    считается от первого понедельника ОТОБРАЖАЕМОГО месяца — правило, которое
    к ленте отношения не имеет вовсе. До 16.09.2026 лента звала ту же функцию
    с окном в 148 дней и получала из неё ОДНУ неделю (4 события на пять
    месяцев): недельный горизонт формально доезжал, а фактически его не было.
    Разбор — CLAUDE.md, «Неделя в ленте».

    Расчёт при этом общий: обе ветки зовут _moon_passages_between выше.
    """
    cusps = _extract_cusps(natal_profile)
    if all(c == 0.0 for c in cusps):
        return []
    win_start = datetime(from_date.year, from_date.month, from_date.day, 0, 0)
    win_end = datetime(to_date.year, to_date.month, to_date.day, 23, 59)
    return _moon_passages_between(
        cusps, win_start, win_end, moon_tz_offset(user_timezone, from_date),
    )


def compute_planner_periods(
    natal_profile: dict,
    from_date: date,
    to_date: date,
    today: Optional[date] = None,
    user_timezone: Optional[str] = None,
    week_offset: Optional[int] = None,
    with_moon_week: bool = True,
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

    # Границы месяца и «сегодня» — местные сутки, переведённые в наивный UTC
    # движка: сравниваются с границами проходов, а они в UTC.
    tz = _zone(user_timezone)
    period_start_dt = _day_start_utc(from_date, tz)
    period_end_dt = _day_start_utc(to_date + timedelta(days=1), tz) - timedelta(minutes=1)
    # Местный полдень текущего дня — для пометки «текущего» периода (E1: Free-витрина планера)
    today_dt = _day_start_utc(today, tz) + timedelta(hours=12)

    # ── Быстрые планеты: Солнце, Меркурий, Венера, Марс — на весь месяц ──
    fast_result = []
    for planet in ("Sun", "Mercury", "Venus", "Mars"):
        # Периоды, пересекающиеся с месяцем, с настоящими границами (house_periods).
        # Если смотрим текущий/будущий месяц (period_end_dt >= today) — дополнительно
        # прячем период, который уже полностью завершился к сегодняшнему дню (иначе
        # карточка показывает истёкшую дату вместо актуального дома). При просмотре
        # прошлого месяца (Pro-навигация назад) это ограничение не действует.
        hide_fully_past = period_end_dt >= today_dt
        passages = [
            p for p in house_periods(planet, cusps, period_start_dt, period_end_dt)
            if not hide_fully_past or p["end_dt"] >= today_dt
        ]
        name_ru, key, emoji = PLANET_NAMES_RU[planet]
        fast_result.append({
            "planet_name":    name_ru,
            "planet_key":     key,
            "emoji":          emoji,
            "planet_subtitle": PLANET_SUBTITLES.get(planet, ""),
            "periods": [
                {
                    "period": _fmt_period(_local(p["start_dt"], tz), _local(p["end_dt"], tz)),
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
    #
    # ⚠️ with_moon_week=False — режим ленты: ей нужны периоды планет и станции
    # из этой же функции, а проходы Луны она берёт за СВОЁ окно
    # (compute_moon_house_passages). Без этого флага мы считали бы неделю,
    # которую никто не прочитает, — а это ~800 обращений к эфемеридам на
    # каждый запрос ленты (шаг Луны 30 минут).
    tz_offset = moon_tz_offset(user_timezone, today)

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

    moon_week = (
        _moon_passages_between(cusps, week_start_local, week_end_local, tz_offset)
        if with_moon_week else []
    )

    # ── Медленные планеты: Юпитер..Плутон — берём дом на середину месяца ──
    slow_result = []
    for planet in ("Jupiter", "Saturn", "Uranus", "Neptune", "Pluto"):
        # Периоды, пересекающиеся с месяцем, с настоящими границами.
        passages = house_periods(planet, cusps, period_start_dt, period_end_dt, step_hours=72)
        name_ru, key, emoji = PLANET_NAMES_RU[planet]
        # Берём период, который реально содержит "сегодня" — раньше здесь ошибочно
        # выбирался самый длинный по продолжительности из пересекающихся с месяцем,
        # из-за чего при переходе в более короткий (по времени пребывания) дом
        # оставался старый, уже завершившийся период (баг с истёкшими датами).
        # В ретроградной петле «сегодня» лежит в двух периодах сразу (они
        # перекрываются, _merge_loops) — берём дом, где планета сейчас.
        now_in = [p for p in passages if p["start_dt"] <= today_dt <= p["end_dt"]]
        if len(now_in) > 1:
            here = _planet_house_at(PLANETS[planet], today_dt, cusps)
            now_in = [p for p in now_in if p["house"] == here] or now_in
        main = now_in[0] if now_in else None
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
            "period_label":    f'{_local(main["start_dt"], tz):%d.%m.%Y} — {_local(main["end_dt"], tz):%d.%m.%Y}',
            "planet_subtitle": PLANET_SUBTITLES.get(planet, ""),
            # См. комментарий у fast_planets выше — настоящие границы для ленты.
            "start_dt": main["start_dt"].isoformat(),
            "end_dt":   main["end_dt"].isoformat(),
        })

    return {
        "fast_planets": fast_result,
        "moon_week":    moon_week,
        "slow_planets": slow_result,
        "retrogrades":  compute_retrograde_stations(from_date, to_date, tz),
        "week_nav": {
            "week_offset": resolved_week_offset,
            "total_weeks": total_weeks,
            "week_start":  week_start_local.date().isoformat(),
            "week_end":    week_end_local.date().isoformat(),
        },
    }
