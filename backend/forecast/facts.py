"""Факты для прогнозов: что делает Луна в местные сутки и что происходит в фазу.

Синхронный модуль (Swiss Ephemeris): из async-ручки — только через
`asyncio.to_thread` (CLAUDE.md, раздел про Swiss Ephemeris).

Карта без времени рождения (`time_unknown`) — урезанный режим, решение
владельца 23.09.2026: без домов и без касаний к натальной Луне, ASC и MC.
Дома, Луна и углы при неизвестном времени сдвинуты до ±6°, а орб транзита —
2°: такие касания были бы шумом, выданным за событие дня. ASC и MC и без того
не входят в `chart.planets`, которые сканирует движок, — отдельно их убирать
не из чего.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from backend.ephemeris.aspects import ASPECTS, _angular_distance
from backend.calendar.lunar_engine import _sign as _sign_ru  # русские названия, как у ленты
from backend.ephemeris.calculator import PLANETS, _calc_planet_position, _datetime_to_jd, _find_house
from backend.forecast.meanings import TONE
from backend.transit.engine import TRANSIT_ORBS, calculate_transits

# Сколько вперёд от фазы смотреть напряжённые касания для блока предупреждения.
LUNATION_WARNING_DAYS = 7
_WARNING_PLANETS = ["Sun", "Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto"]


def _natal_targets(chart) -> list[dict]:
    # Один набор точек на проект (шаг 5 аудита): с ASC и MC, без Юж. узла;
    # к узлам — только соединение и оппозиция (day_event.counts).
    from backend.day_event import points
    return points(chart)


def _cusps(chart) -> list[float] | None:
    from backend.chart_points import cusps
    return cusps(chart)


def _utc_naive(dt_local: datetime) -> datetime:
    return dt_local.astimezone(timezone.utc).replace(tzinfo=None)


@dataclass
class DayFacts:
    local_date: date
    trimmed: bool
    moon_sign: str
    houses: list[int] = field(default_factory=list)      # по порядку за день, без повторов
    aspects: list[dict] = field(default_factory=list)    # {natal, aspect, tone}
    # Главное событие дня (day_event.main_event) — первый факт прогноза,
    # даже если это не Луна (решение владельца 02.10.2026, проверка c2).
    # {transit, natal, aspect, tone} или {phase}; None — события нет.
    main: dict | None = None
    sky: bool = False   # флаг sky_event — термины промпта (шаг 9.5)


def sky_on(chart) -> bool:
    """Флаг `sky_event` владельца карты (задание 4.3). Через атрибут модуля, а
    не импортом имени: прогон согласованности `--sky on` подменяет
    `day_event._sky_on`, и прогноз должен видеть подмену, как главное событие."""
    from backend import day_event
    return day_event._sky_on(chart)


def _moon_touches(chart, local_date: date, tz: ZoneInfo, sky: bool):
    """(натальная точка, аспект, aware UTC) — касания Луны в местные сутки.

    `sky` — из ядра (`sky_events`, только корни: станция — не касание), сутки
    — `local_day`. Иначе — старый движок, как до 4.3."""
    if sky:
        from backend.sky import sky_events
        from backend.time_utils import local_day
        s, e = local_day(local_date, tz.key)
        for ev in sky_events(chart, s, e):
            if ev.transit == "Moon":
                for t in ev.touches:
                    if s <= t.at_utc < e:
                        yield ev.natal, ev.aspect, t.at_utc
        return
    from backend.day_event import counts
    start = _utc_naive(datetime(local_date.year, local_date.month, local_date.day, tzinfo=tz))
    end = start + timedelta(days=1)
    # Движок сканирует по календарным датам UTC; окно берётся с запасом в день
    # с каждой стороны, а в сутки попадает только то, чей ТОЧНЫЙ момент внутри.
    for e in calculate_transits(
        natal_planets=_natal_targets(chart),
        from_date=start.date() - timedelta(days=1),
        to_date=end.date() + timedelta(days=1),
        planet_filter=["Moon"],
    ):
        if not e.exact_date or not counts(e.natal_planet, e.aspect_type):
            continue
        exact = datetime.fromisoformat(e.exact_date)
        if start <= exact < end:
            yield e.natal_planet, e.aspect_type, exact.replace(tzinfo=timezone.utc)


def compute_day(chart, local_date: date, tz: ZoneInfo, daily_time=None, quiet_from=None,
                sky: bool | None = None) -> DayFacts:
    """`daily_time`/`quiet_from` — окно уведомлений человека: главное событие
    дня зависит от него (day_event.main_event), и прогноз обязан назвать то
    же событие, что утренний пуш.

    `sky` — касания из ядра (флаг `sky_event`, задание 4.3); None — по флагу
    владельца карты. ⚠️ Касания Луны и главное событие — из ОДНОГО источника:
    иначе минута главного касания разошлась бы со списком Луны, и оно не
    убралось бы из него — повторилось бы вторым пунктом."""
    from backend.day_event import SLOW, main_event

    if sky is None:
        sky = sky_on(chart)
    start = _utc_naive(datetime(local_date.year, local_date.month, local_date.day, tzinfo=tz))

    aspects, seen = [], set()
    for natal, aspect, _ in sorted(_moon_touches(chart, local_date, tz, sky), key=lambda x: x[2]):
        if (natal, aspect) in seen:
            continue
        seen.add((natal, aspect))
        aspects.append({"natal": natal, "aspect": aspect, "tone": TONE[aspect]})

    main = None
    ev = main_event(chart, local_date, tz.key, daily_time, quiet_from, sky)
    if ev is not None and ev.natal is None:
        main = {"phase": ev.transit}
    elif ev is not None:
        main = {"transit": ev.transit, "natal": ev.natal, "aspect": ev.aspect,
                "tone": TONE[ev.aspect], "slow": ev.transit in SLOW}
        if ev.transit == "Moon":
            # То же касание Луны — не повторять вторым пунктом.
            aspects = [a for a in aspects if (a["natal"], a["aspect"]) != (ev.natal, ev.aspect)]

    moon_id = PLANETS["Moon"]
    noon = start + timedelta(hours=12)
    moon_lon, *_ = _calc_planet_position(moon_id, round(_datetime_to_jd(noon), 6))
    moon_sign = _sign_ru(moon_lon)

    houses: list[int] = []
    cusps = _cusps(chart)
    if cusps:
        for h in range(0, 24, 2):
            lon, *_ = _calc_planet_position(moon_id, round(_datetime_to_jd(start + timedelta(hours=h)), 6))
            house = _find_house(lon, cusps)
            if house not in houses:
                houses.append(house)

    return DayFacts(
        local_date=local_date, trimmed=bool(chart.time_unknown),
        moon_sign=moon_sign, houses=houses, aspects=aspects, main=main, sky=sky,
    )


@dataclass
class LunationFacts:
    phase: str                     # new_moon | full_moon
    at_utc: datetime
    at_local: datetime
    sign: str
    trimmed: bool
    house: int | None
    aspects: list[dict] = field(default_factory=list)   # {planet, natal, tone}
    warnings: list[dict] = field(default_factory=list)  # {planet, natal, date: date}
    sky: bool = False   # флаг sky_event — термины промпта (шаг 9.5)


def find_phase(phase: str, near: date) -> datetime | None:
    """Момент фазы `phase` рядом с датой `near` (±2 суток), aware UTC —
    из lunations, одной функции фаз на проект."""
    from backend.calendar.lunar_engine import lunations

    start = datetime(near.year, near.month, near.day, tzinfo=timezone.utc) - timedelta(days=2)
    found = lunations(start, start + timedelta(days=5), types=(phase,))
    noon = datetime(near.year, near.month, near.day, 12, tzinfo=timezone.utc)
    return min((x.at for x in found), key=lambda m: abs(m - noon), default=None)


def compute_lunation(chart, phase: str, at_utc: datetime, tz: ZoneInfo,
                     sky: bool | None = None) -> LunationFacts:
    """`sky` — предупреждения из ядра (флаг `sky_event`, задание 4.3); None —
    по флагу владельца карты. Касания в момент фазы (`aspects`) — орб в одну
    минуту, ядру там заменять нечего."""
    if sky is None:
        sky = sky_on(chart)
    naive = at_utc.astimezone(timezone.utc).replace(tzinfo=None)
    jd = round(_datetime_to_jd(naive), 6)
    moon_lon, *_ = _calc_planet_position(PLANETS["Moon"], jd)
    sign = _sign_ru(moon_lon)

    from backend.day_event import counts

    targets = _natal_targets(chart)
    aspects = []
    for t_name, t_id in PLANETS.items():
        if t_name == "North Node":
            continue
        t_lon, *_ = _calc_planet_position(t_id, jd)
        for p in targets:
            angle = _angular_distance(t_lon, p["longitude"])
            for asp, exact in ASPECTS.items():
                if abs(angle - exact) <= TRANSIT_ORBS[asp] and counts(p["name"], asp):
                    aspects.append({"planet": t_name, "natal": p["name"], "tone": TONE[asp]})

    cusps = _cusps(chart)
    house = _find_house(moon_lon, cusps) if cusps else None

    # Напряжённые касания в ближайшую неделю — с датами, посчитанными здесь.
    # Модели эти даты передаются готовыми; своих она не придумывает
    # (validate.py сверяет каждую дату в тексте с этим списком).
    start = naive.date()
    warnings, seen = [], set()
    for planet, natal, aspect, exact in _warning_touches(chart, targets, start, tz, sky):
        if TONE[aspect] != "tense":
            continue
        d = exact.astimezone(tz).date()
        if not (start <= d <= start + timedelta(days=LUNATION_WARNING_DAYS)):
            continue
        key = (planet, natal)
        if key in seen:
            continue
        seen.add(key)
        warnings.append({"planet": planet, "natal": natal, "date": d})
    warnings.sort(key=lambda w: w["date"])

    return LunationFacts(
        phase=phase, at_utc=at_utc, at_local=at_utc.astimezone(tz), sign=sign,
        trimmed=bool(chart.time_unknown), house=house,
        aspects=aspects, warnings=warnings[:3], sky=sky,
    )


def _warning_touches(chart, targets, start: date, tz: ZoneInfo, sky: bool):
    """(планета, натальная точка, аспект, aware UTC) — касания для предупреждений.

    ⚠️ Отбор по дате — в `compute_lunation`, одинаковый в обоих режимах (от
    UTC-даты фазы `start`, по местной дате касания): под флагом меняется
    только источник касаний. Ядро — по времени, чтобы `seen` взял первое
    касание петли; иначе — старый движок, как до 4.3."""
    if sky:
        from backend.sky import sky_events
        from backend.time_utils import local_day
        s = local_day(start, tz.key)[0]
        e = local_day(start + timedelta(days=LUNATION_WARNING_DAYS), tz.key)[1]
        yield from sorted(((ev.transit, ev.natal, ev.aspect, t.at_utc)
                           for ev in sky_events(chart, s, e) if ev.transit in _WARNING_PLANETS
                           for t in ev.touches if s <= t.at_utc < e), key=lambda x: x[3])
        return
    from backend.day_event import counts
    for e in calculate_transits(
        natal_planets=targets, from_date=start,
        to_date=start + timedelta(days=LUNATION_WARNING_DAYS),
        planet_filter=_WARNING_PLANETS,
    ):
        if e.exact_date and counts(e.natal_planet, e.aspect_type):
            yield (e.transit_planet, e.natal_planet, e.aspect_type,
                   datetime.fromisoformat(e.exact_date).replace(tzinfo=timezone.utc))
