"""Главное событие дня — ОДНО правило для пуша, виджета и карточек.

Решение владельца 01.10.2026 (флаг `push_day_event`). Сегодня зовёт только
утренний пуш (`push/cron.py`); виджет, «Неделя вперёд» и карточка для сторис
обязаны звать эту же функцию, а не заводить свой отбор: иначе пуш скажет
«в 14:20 Луна к Сатурну», а виджет в тот же день — другое.

Синхронный модуль (Swiss Ephemeris): из async-ручки — только через
`asyncio.to_thread` (backend/CLAUDE.md).

Кандидаты — события, чей ТОЧНЫЙ момент лежит в местных сутках:
  * касание транзитной планеты (включая Луну) к натальной точке;
  * новолуние и полнолуние.

Отбор:
  1. Окно бодрствования — `in_send_window` (push/cron.py, та же функция, что
     у планировщика). ⚠️ Вне окна событие не главное ни для кого, даже для
     виджета: иначе виджет показал бы «в 03:10», а пуш — другое событие.
     Исключение — медленные планеты (`SLOW`): их касание длится сутками,
     время в тексте не называется (`DayEvent.timed = False`).
  2. Балл = вес транзитной планеты × вес натальной точки × вес аспекта.
     Фаза Луны — `LUNATION_SCORE`: выше любого касания Луны (максимум 9),
     ниже медленной планеты к личной точке.
  3. Равный балл — ближе к середине окна, затем по ключу: результат обязан
     быть одинаковым при каждом вызове, иначе пуш и виджет разойдутся.

Карта без времени рождения — как в forecast/facts.py: без натальной Луны,
ASC и MC (они сдвинуты до ±6°, касание было бы шумом, выданным за событие).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from backend.ephemeris.ru_names import PLANET_RU

WEIGHT_TRANSIT = {
    "Pluto": 5, "Neptune": 5, "Uranus": 5, "Saturn": 5, "Jupiter": 4,
    "Mars": 3, "Sun": 2, "Venus": 2, "Mercury": 2, "Moon": 1,
}
WEIGHT_NATAL = {
    "Sun": 3, "Moon": 3, "Ascendant": 3, "Midheaven": 3,
    "Mercury": 2, "Venus": 2, "Mars": 2,
}  # остальные — 1
WEIGHT_ASPECT = {"conjunction": 3, "opposition": 2.5, "square": 2.5, "trine": 2, "sextile": 1}
SLOW = {"Jupiter", "Saturn", "Uranus", "Neptune", "Pluto"}
LUNATION_SCORE = 12
NATAL_PLANETS = ("Sun", "Moon", "Mercury", "Venus", "Mars",
                 "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto")

# Натальная точка с «твой» в дательном: «Луна к твоему Сатурну».
_YOURS_DAT = {
    "Sun": "твоему Солнцу", "Moon": "твоей Луне", "Mercury": "твоему Меркурию",
    "Venus": "твоей Венере", "Mars": "твоему Марсу", "Jupiter": "твоему Юпитеру",
    "Saturn": "твоему Сатурну", "Uranus": "твоему Урану", "Neptune": "твоему Нептуну",
    "Pluto": "твоему Плутону", "Ascendant": "твоему Асценденту",
    "Midheaven": "твоей Середине неба",
}
# Тон — ASPECT_TONE движка. Без рода: пола человека мы не знаем (CLAUDE.md).
_TONE_TAIL = {
    "harmonious": "хороший момент для шага вперёд.",
    "tense": "лучше не торопиться и не спорить.",
    "new_cycle": "время начать новое.",
}
_LUNATION_RU = {"new_moon": "новолуние", "full_moon": "полнолуние"}
_LUNATION_TAIL = {
    "new_moon": "время решить, с чего начать.",
    "full_moon": "время увидеть итог месяца.",
}


@dataclass(frozen=True)
class DayEvent:
    key: str             # устойчив между вызовами: что, к чему, когда (UTC)
    at_local: datetime   # точный момент, aware, пояс человека
    transit: str         # планета или new_moon / full_moon
    natal: str | None
    aspect: str | None
    score: float
    timed: bool          # момент в окне — время можно назвать в тексте


def _targets(chart) -> list[dict]:
    out = [
        {"name": p["name"], "longitude": p["longitude"], "sign": p.get("sign", "")}
        for p in (chart.planets or [])
        if p.get("name") in NATAL_PLANETS and p.get("longitude") is not None
        and not (chart.time_unknown and p["name"] == "Moon")
    ]
    if not chart.time_unknown:
        from backend.transit.house_passages import _extract_cusps
        cusps = _extract_cusps({"houses": chart.houses})
        if not all(c == 0.0 for c in cusps):
            out += [{"name": "Ascendant", "longitude": cusps[0], "sign": ""},
                    {"name": "Midheaven", "longitude": cusps[9], "sign": ""}]
    return out


def _candidates(chart, local_date: date, tz: ZoneInfo) -> list[DayEvent]:
    from backend.push.cron import _phases_on_local_date
    from backend.transit.engine import calculate_transits

    start = datetime(local_date.year, local_date.month, local_date.day, tzinfo=tz)
    nxt = local_date + timedelta(days=1)
    end = datetime(nxt.year, nxt.month, nxt.day, tzinfo=tz)
    s_utc = start.astimezone(timezone.utc).replace(tzinfo=None)
    e_utc = end.astimezone(timezone.utc).replace(tzinfo=None)

    out: dict[str, DayEvent] = {}
    # Движок сканирует календарные даты UTC — окно с запасом в день с каждой
    # стороны, в сутки попадает только то, чей точный момент внутри.
    for e in calculate_transits(natal_planets=_targets(chart),
                                from_date=s_utc.date() - timedelta(days=1),
                                to_date=e_utc.date() + timedelta(days=1)):
        if not e.exact_date:
            continue
        exact = datetime.fromisoformat(e.exact_date)
        if not (s_utc <= exact < e_utc):
            continue
        key = f"{e.transit_planet}:{e.natal_planet}:{e.aspect_type}:{e.exact_date}"
        out[key] = DayEvent(
            key=key, at_local=exact.replace(tzinfo=timezone.utc).astimezone(tz),
            transit=e.transit_planet, natal=e.natal_planet, aspect=e.aspect_type,
            score=WEIGHT_TRANSIT[e.transit_planet] * WEIGHT_NATAL.get(e.natal_planet, 1)
            * WEIGHT_ASPECT[e.aspect_type],
            timed=True,
        )
    for ph in _phases_on_local_date(local_date, str(tz)):
        at = datetime.strptime(f"{ph.date} {ph.time[:5]}", "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
        key = f"{ph.type}:{ph.date}"
        out[key] = DayEvent(key=key, at_local=at.astimezone(tz), transit=ph.type,
                            natal=None, aspect=None, score=LUNATION_SCORE, timed=True)
    return list(out.values())


def main_event(chart, local_date: date, tzname: str, daily_time, quiet_from) -> DayEvent | None:
    """Главное событие местных суток `local_date` или None."""
    from backend.push.cron import DEFAULT_TZ, _parse_hm, in_send_window

    try:
        tz = ZoneInfo(tzname)
    except Exception:
        tz = ZoneInfo(DEFAULT_TZ)
    lo = _parse_hm(daily_time, (8, 0))
    hi = _parse_hm(quiet_from, (22, 0))
    mid = ((lo[0] * 60 + lo[1]) + (hi[0] * 60 + hi[1])) / 2

    best = None
    for ev in _candidates(chart, local_date, tz):
        if not in_send_window(ev.at_local, daily_time, quiet_from):
            if ev.transit not in SLOW:
                continue
            ev = DayEvent(**{**ev.__dict__, "timed": False})
        rank = (-ev.score, abs(ev.at_local.hour * 60 + ev.at_local.minute - mid), ev.key)
        if best is None or rank < best[0]:
            best = (rank, ev)
    return best[1] if best else None


def phrase(ev: DayEvent) -> str:
    """«Сегодня в 14:20 Луна к твоему Сатурну — …» для утреннего пуша."""
    when = f"Сегодня в {ev.at_local:%H:%M}" if ev.timed else "Сегодня точный аспект:"
    if ev.natal is None:
        return f"{when} {_LUNATION_RU[ev.transit]} — {_LUNATION_TAIL[ev.transit]}"
    from backend.transit.engine import ASPECT_TONE
    tail = _TONE_TAIL[ASPECT_TONE.get(ev.aspect, "tense")]
    return f"{when} {PLANET_RU[ev.transit]} к {_YOURS_DAT[ev.natal]} — {tail}"


def short(ev: DayEvent) -> str:
    """Фрагмент для склейки утреннего пуша с другими событиями."""
    when = f"в {ev.at_local:%H:%M} " if ev.timed else ""
    if ev.natal is None:
        return f"{when}{_LUNATION_RU[ev.transit]}"
    return f"{when}{PLANET_RU[ev.transit]} к {_YOURS_DAT[ev.natal]}"
