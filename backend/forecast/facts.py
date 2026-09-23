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


def resolve_tz(tz_name: str | None, chart_tz: str | None) -> ZoneInfo:
    """Пояс телефона, если он пришёл и настоящий; иначе пояс карты; иначе UTC.

    Граница дня по поясу ТЕЛЕФОНА (решение владельца 23.09.2026): человек,
    родившийся в Москве и живущий в Новосибирске, открывает «сегодня» по
    своим часам. Уведомления на это ещё не переведены — TASKS.md.
    """
    for name in (tz_name, chart_tz):
        if not name:
            continue
        try:
            return ZoneInfo(name)
        except Exception:
            continue
    return ZoneInfo("UTC")


def _natal_targets(chart) -> list[dict]:
    planets = chart.planets or []
    if chart.time_unknown:
        return [p for p in planets if p.get("name") != "Moon"]
    return list(planets)


def _cusps(chart) -> list[float] | None:
    if chart.time_unknown:
        return None
    from backend.transit.house_passages import _extract_cusps
    cusps = _extract_cusps({"houses": chart.houses})
    return None if all(c == 0.0 for c in cusps) else cusps


def _utc_naive(dt_local: datetime) -> datetime:
    return dt_local.astimezone(timezone.utc).replace(tzinfo=None)


@dataclass
class DayFacts:
    local_date: date
    trimmed: bool
    moon_sign: str
    houses: list[int] = field(default_factory=list)      # по порядку за день, без повторов
    aspects: list[dict] = field(default_factory=list)    # {natal, tone}


def compute_day(chart, local_date: date, tz: ZoneInfo) -> DayFacts:
    start = _utc_naive(datetime(local_date.year, local_date.month, local_date.day, tzinfo=tz))
    end = start + timedelta(days=1)

    # Движок сканирует по календарным датам UTC; окно берётся с запасом в день
    # с каждой стороны, а в сутки попадает только то, чей ТОЧНЫЙ момент внутри.
    events = calculate_transits(
        natal_planets=_natal_targets(chart),
        from_date=start.date() - timedelta(days=1),
        to_date=end.date() + timedelta(days=1),
        planet_filter=["Moon"],
    )
    aspects, seen = [], set()
    for e in sorted(events, key=lambda e: e.exact_date or ""):
        if not e.exact_date:
            continue
        exact = datetime.fromisoformat(e.exact_date)
        if not (start <= exact < end):
            continue
        key = (e.natal_planet, e.aspect_type)
        if key in seen:
            continue
        seen.add(key)
        aspects.append({"natal": e.natal_planet, "tone": TONE[e.aspect_type]})

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
        moon_sign=moon_sign, houses=houses, aspects=aspects,
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


def find_phase(phase: str, near: date) -> datetime | None:
    """Момент фазы `phase` рядом с датой `near` (±2 суток), aware UTC."""
    from backend.calendar.lunar_engine import _find_phase, _jd, jd_to_utc

    target = 0.0 if phase == "new_moon" else 180.0
    found = _find_phase(_jd(near - timedelta(days=2), 0.0), _jd(near + timedelta(days=2), 24.0), target)
    if not found:
        return None
    moments = [jd_to_utc(jd) for jd in found]
    noon = datetime(near.year, near.month, near.day, 12, tzinfo=timezone.utc)
    return min(moments, key=lambda m: abs(m - noon))


def compute_lunation(chart, phase: str, at_utc: datetime, tz: ZoneInfo) -> LunationFacts:
    naive = at_utc.astimezone(timezone.utc).replace(tzinfo=None)
    jd = round(_datetime_to_jd(naive), 6)
    moon_lon, *_ = _calc_planet_position(PLANETS["Moon"], jd)
    sign = _sign_ru(moon_lon)

    targets = _natal_targets(chart)
    aspects = []
    for t_name, t_id in PLANETS.items():
        if t_name == "North Node":
            continue
        t_lon, *_ = _calc_planet_position(t_id, jd)
        for p in targets:
            angle = _angular_distance(t_lon, p["longitude"])
            for asp, exact in ASPECTS.items():
                if abs(angle - exact) <= TRANSIT_ORBS[asp]:
                    aspects.append({"planet": t_name, "natal": p["name"], "tone": TONE[asp]})

    cusps = _cusps(chart)
    house = _find_house(moon_lon, cusps) if cusps else None

    # Напряжённые касания в ближайшую неделю — с датами, посчитанными здесь.
    # Модели эти даты передаются готовыми; своих она не придумывает
    # (validate.py сверяет каждую дату в тексте с этим списком).
    start = naive.date()
    events = calculate_transits(
        natal_planets=targets, from_date=start,
        to_date=start + timedelta(days=LUNATION_WARNING_DAYS),
        planet_filter=_WARNING_PLANETS,
    )
    warnings, seen = [], set()
    for e in events:
        if TONE[e.aspect_type] != "tense" or not e.exact_date:
            continue
        exact_local = datetime.fromisoformat(e.exact_date).replace(tzinfo=timezone.utc).astimezone(tz)
        d = exact_local.date()
        if not (start <= d <= start + timedelta(days=LUNATION_WARNING_DAYS)):
            continue
        key = (e.transit_planet, e.natal_planet)
        if key in seen:
            continue
        seen.add(key)
        warnings.append({"planet": e.transit_planet, "natal": e.natal_planet, "date": d})
    warnings.sort(key=lambda w: w["date"])

    return LunationFacts(
        phase=phase, at_utc=at_utc, at_local=at_utc.astimezone(tz), sign=sign,
        trimmed=bool(chart.time_unknown), house=house,
        aspects=aspects, warnings=warnings[:3],
    )
