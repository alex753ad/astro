"""backend/calendar/engine.py

Движок общего астро-календаря (бесплатный уровень).
Вычисляет ключевые события месяца БЕЗ натальной карты:
  - Новолуния и Полнолуния
  - Ингрессы планет (смена знака)
  - Точные аспекты между медленными планетами
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
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


def jd_to_utc(jd: float) -> datetime:
    """Julian Day → момент как aware-datetime в UTC.

    ЕДИНСТВЕННАЯ точка, где момент перестаёт быть числом и становится
    временем. Заведена под ленту (backend/feed/), но существующие
    форматтеры ниже переведены на неё же — иначе в проекте осталось бы
    два независимых способа превратить JD во время, и они разъехались бы
    ровно так, как уже разъехались пояса.

    Почему это важно: `swe.revjul` отдаёт УТЦ-компоненты, и раньше каждый
    потребитель сам решал, что с ними делать — `_jd_to_dt` подписывал их
    «UTC», `_jd_to_gmt3` и фазы Луны в main.py вручную прибавляли три часа
    (арифметикой, не таймзоной). В результате затмения и фазы одного и того
    же календаря приходили в РАЗНЫХ поясах, расхождение до 3 часов, а у
    события около полуночи уезжала и дата. Это находка 3.7 из CLAUDE.md.

    Дробная часть часа переводится в секунды УСЕЧЕНИЕМ, а не округлением, и
    это не небрежность: все три прежних форматтера брали `int()` и от часов,
    и от минут. Округление сдвинуло бы отображаемую минуту у моментов вида
    59.7 секунды — то есть поменяло бы строки, которые уже отдаёт
    /calendar/lunar. Секунды при этом сохраняются: для показа они не нужны,
    для сортировки ленты по времени — нужны.
    """
    y, mo, d, h_float = swe.revjul(jd)
    total_seconds = int(h_float * 3600)
    # revjul может отдать 24:00:00 на границе суток — timedelta переносит сам,
    # без ручной возни с длиной месяца, как это было в _jd_to_gmt3 ниже.
    return datetime(int(y), int(mo), int(d), tzinfo=timezone.utc) + timedelta(seconds=total_seconds)


def _jd_to_dt(jd: float) -> tuple[str, str]:
    """JD → ("YYYY-MM-DD", "HH:MM") в UTC. Формат сохранён дословно:
    строки уходят наружу в /calendar/lunar, менять их нельзя."""
    dt = jd_to_utc(jd)
    return dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M")

def _lon(jd: float, planet: str) -> float:
    r, _ = swe.calc_ut(jd, PLANET_IDS[planet], swe.FLG_SWIEPH)
    return r[0]

def _sign(lon: float) -> str:
    return ZODIAC_SIGNS[int(lon // 30) % 12]

def _diff(a: float, b: float) -> float:
    d = (a - b) % 360
    return d - 360 if d > 180 else d


# ── Moon phases ───────────────────────────────────────────────────────────────

# Допуск, по которому найденный момент признаётся настоящей фазой.
# Десять градусов — как в такой же проверке для /calendar/lunar (main.py,
# _compute_lunar_calendar): настоящее пересечение бисекция находит с точностью
# до секунд, то есть фактический угол отличается от цели на доли градуса, а
# ложное срабатывание промахивается на все 180.
_PHASE_TOLERANCE_DEG = 10


def _find_phase(jd_start: float, jd_end: float, target: float) -> list[float]:
    """Моменты, когда угол Луна−Солнце проходит `target` (0° или 180°).

    ⚠️ Проверка найденного момента обязательна, и её отсутствие было
    настоящим дефектом, а не теоретическим. Условие `prev * val < 0` ловит
    смену знака, а знак меняется ДВАЖДЫ за оборот: в самой фазе и на
    противоположной точке орбиты, где величина перескакивает с +180 на −180.
    Второй случай — не фаза, но бисекция послушно сходилась к границе шага и
    возвращала момент с круглым временем (00:00 или 12:00 UTC).

    Что это давало до 04.09.2026: get_moon_phases отдавала ЧЕТЫРЕ фазы в
    месяц вместо двух — на каждое новолуние фантомное полнолуние в тот же
    день и наоборот. Дедуп по датам в get_moon_phases их не ловил: он
    сравнивает даты внутри ОДНОГО типа, а у фантома дата отличается от
    настоящей фазы того же типа.

    Кто это видел. Пуши (push/cron.py, гейт push_moon_phases): 10 сентября
    2026 пользователю уходило два уведомления разом — «Новолуние завтра» и
    «Полнолуние завтра», — а 27-го ещё одно, про новолуние, которого не
    существует. Еженедельное письмо (email_service.py) перечисляло фантомы в
    блоке лунных фаз. Лунная страница задета почти не была: она предпочитает
    /calendar/lunar, а тот считает фазы своим циклом в main.py — с такой же
    проверкой, которой здесь не хватало.

    ⚠️ Проверка в main.py остаётся на месте: этот модуль и
    _compute_lunar_calendar считают фазы независимо друг от друга, и вторая
    проверка там не дубль этой, а защита второго расчёта.
    """
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
            found = (lo + hi) / 2
            angle = (_lon(found, "Moon") - _lon(found, "Sun")) % 360
            if abs((angle - target + 180) % 360 - 180) <= _PHASE_TOLERANCE_DEG:
                results.append(found)
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
        seen_dates = set()
        for jd in found:
            dt, tm = _jd_to_dt(jd)
            # Фильтр: только даты текущего месяца, без дублей
            event_month = int(dt[5:7])
            event_year  = int(dt[:4])
            if event_year != year or event_month != month:
                continue
            if dt in seen_dates:
                continue
            seen_dates.add(dt)
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


# ── Eclipses ──────────────────────────────────────────────────────────────────

_SOLAR_KIND_FLAGS = [
    (swe.ECL_TOTAL, "total"),
    (swe.ECL_ANNULAR_TOTAL, "annular"),
    (swe.ECL_ANNULAR, "annular"),
    (swe.ECL_PARTIAL, "partial"),
]
_LUNAR_KIND_FLAGS = [
    (swe.ECL_TOTAL, "total"),
    (swe.ECL_PARTIAL, "partial"),
    (swe.ECL_PENUMBRAL, "penumbral"),
]


def _eclipse_kind(retflag: int, flags: list[tuple[int, str]]) -> str:
    for flag, kind in flags:
        if retflag & flag:
            return kind
    return "partial"


@dataclass
class EclipseEvent:
    date: str
    time: str
    type: str  # solar | lunar
    kind: str  # total | partial | annular | penumbral

    def to_dict(self) -> dict:
        return {"date": self.date, "time": self.time, "type": self.type, "kind": self.kind}


def _scan_eclipses(jd_start: float, jd_end: float, finder, flags, etype: str) -> list[EclipseEvent]:
    events: list[EclipseEvent] = []
    jd = jd_start
    for _ in range(50):  # предохранитель от зацикливания
        if jd >= jd_end:
            break
        try:
            retflag, tret = finder(jd, swe.FLG_SWIEPH, 0, False)
        except Exception:
            break
        if retflag < 0 or tret[0] <= 0:
            break
        if tret[0] > jd_end:
            break
        dt, tm = _jd_to_dt(tret[0])
        events.append(EclipseEvent(date=dt, time=f"{tm} UTC", type=etype,
                                    kind=_eclipse_kind(retflag, flags)))
        jd = tret[0] + 1
    return events


def get_eclipses(start: date, end: date) -> list[dict]:
    """Солнечные и лунные затмения в диапазоне [start, end] (включительно)."""
    jd_start = _jd(start, 0)
    jd_end = _jd(end, 24)
    events = (
        _scan_eclipses(jd_start, jd_end, swe.sol_eclipse_when_glob, _SOLAR_KIND_FLAGS, "solar")
        + _scan_eclipses(jd_start, jd_end, swe.lun_eclipse_when, _LUNAR_KIND_FLAGS, "lunar")
    )
    events.sort(key=lambda e: (e.date, e.time))
    return [e.to_dict() for e in events]


# ── Равноденствия и солнцестояния ──────────────────────────────

# Четыре точки, в которых долгота Солнца проходит кардинальные градусы. Это те же
# самые моменты, что и вход Солнца в Овна/Рака/Весы/Козерога, то есть четыре из
# двенадцати ингрессов Солнца, которые уже умеет считать get_ingresses(). Отдельная
# функция, а не фильтр по её выводу, потому что get_ingresses сканирует шесть
# планет сразу, а /calendar/lunar дергается на каждом открытии страницы — платить
# за Меркурий/Венеру/Марс/Юпитер/Сатурн ради четырёх дат в году незачем.
SOLAR_EVENTS = [
    (0,   "equinox_spring",  "🌸", "Весеннее равноденствие"),
    (90,  "solstice_summer", "☀️", "Летнее солнцестояние"),
    (180, "equinox_autumn",  "🍂", "Осеннее равноденствие"),
    (270, "solstice_winter", "❄️", "Зимнее солнцестояние"),
]


def _jd_to_gmt3(jd: float) -> tuple[str, str]:
    """JD → ("YYYY-MM-DD", "HH:MM") в GMT+3.

    Отдельная от _jd_to_dt(), которая отдаёт UTC: равноденствия обязаны
    лечь в ту же клетку сетки, что и фазы Луны, а те считаются в GMT+3
    (main.py, _compute_lunar_calendar). Два часовых пояса на одной странице
    разъехались бы на событиях около полуночи: значок встал бы на соседний день.

    Здесь раньше лежала копия переноса через сутки/месяц/год из расчёта фаз
    (main.py) — пятнадцать строк ручной арифметики, и в комментарии стояло,
    что копия дешевле выноса. Под ленту момент всё равно понадобился честным
    datetime, поэтому обе копии сведены в jd_to_utc(): перенос делает
    timedelta, а не проверка длины месяца руками.

    Смещение остаётся фиксированным +3 без учёта DST — Москва его не
    переводит с 2014 года, а менять пояс календаря — отдельное решение, не
    побочный эффект этой правки. Выдаваемые строки прежние.
    """
    local = jd_to_utc(jd) + timedelta(hours=3)
    y, mo, d = local.year, local.month, local.day
    hh, mm = local.hour, local.minute
    return f"{y:04d}-{mo:02d}-{d:02d}", f"{hh:02d}:{mm:02d}"


def get_solar_events(year: int, month: int) -> list[dict]:
    """Равноденствия и солнцестояния месяца (обычно пусто — их 4 в году).

    Даты не табличные: календарь листается на произвольные годы, а момент
    плывёт на полторы суток в пределах четырёхлетнего цикла.

    Шаг сканирования — сутки, а не половина, как в _find_phase(): там ищется
    угол Луна−Солнце, меняющийся ~13°/сутки, здесь — долгота одного Солнца,
    ~1°/сутки. Проскочить пересечение при таком шаге невозможно.

    Окно шире месяца на сутки с каждой стороны, а фильтр — по уже
    пересчитанной в GMT+3 дате: событие в 22:30 UTC 31 августа — это 01:30 первого
    сентября по Москве, и показать его надо в сентябре. Тот же приём, что у
    фаз Луны (широкое окно + фильтр по month_prefix).
    """
    jd0 = _jd(date(year, month, 1), 0) - 1
    jd1 = (_jd(date(year + 1, 1, 1), 0) if month == 12
           else _jd(date(year, month + 1, 1), 0)) + 1

    events: list[dict] = []
    for target, etype, emoji, label in SOLAR_EVENTS:
        step = 1.0
        jd, prev = jd0, None
        while jd <= jd1:
            # Разность в диапазоне [-180, 180): пересечение цели — смена знака
            # снизу вверх. Скачок с +180 на −180 на противоположной точке орбиты
            # сюда не попадает: там prev > 0.
            val = (_lon(jd, "Sun") - target + 180) % 360 - 180
            if prev is not None and prev < 0 <= val:
                lo, hi = jd - step, jd
                for _ in range(48):
                    mid = (lo + hi) / 2
                    v = (_lon(mid, "Sun") - target + 180) % 360 - 180
                    if v < 0:
                        lo = mid
                    else:
                        hi = mid
                dt, tm = _jd_to_gmt3((lo + hi) / 2)
                events.append({
                    "date": dt,
                    "time": f"{tm} GMT+3",
                    "type": etype,
                    "emoji": emoji,
                    "description": label,
                })
            prev = val
            jd += step

    month_prefix = f"{year:04d}-{month:02d}-"
    events = [e for e in events if e["date"].startswith(month_prefix)]
    events.sort(key=lambda e: (e["date"], e["time"]))
    return events


# ── Main entry point ──────────────────────────────────────────────────────────

def get_monthly_calendar(year: int, month: int) -> list[dict]:
    """Полный список ключевых событий месяца для общего календаря."""
    events: list[CalendarEvent] = []
    events.extend(get_moon_phases(year, month))
    events.extend(get_ingresses(year, month))
    events.extend(get_slow_aspects(year, month))
    events.sort(key=lambda e: (e.date, e.time))
    return [e.to_dict() for e in events]
