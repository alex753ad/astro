"""Ядро транзитов — SkyEvent (шаг 4 аудита, docs/audit_unified_model.md, 8.2).

ОДНО событие «транзитная планета — аспект — натальная точка» с настоящими
границами: первый вход в орб, окончательный выход, все точные касания. До
ядра каждый раздел резал событие своим окном и своей сеткой (таблица 8.1:
одно событие — пять разных сроков). Потребители переходят на ядро по одному
за флагом `sky_event` (задания 4.2–4.13); пока потребителей нет.

Правила (решения владельца О1–О6, 05.10.2026):
  * орб — `TRANSIT_ORBS` для всех планет (О1);
  * касание — только корень знаковой разности `engine._signed` (О2, тот же
    помощник, что у `_find_exact_aspect` после #120 — своей формулы не
    заводить). Станция рядом с точкой — не касание;
  * событие без касания — только если сближение ≤ 0,5° (`CLOSEST_MAX`, О3):
    `closest` с `exact=False`, «ближе всего — 13 апреля». Дальше — не событие;
  * петля — одно событие: проход склеивается с предыдущим, если планета вошла
    в орб с той стороны, с которой вышла (правило `_merge_loops` шага 2б,
    `house_passages`). С той же стороны вернуться можно только развернувшись:
    обойти круг и войти с той же стороны нельзя, поэтому порога по времени нет.
    Перерывы — в `passes`, касания всех проходов — в `touches`;
  * точки — `day_event.points/counts` (без времени рождения — без натальной
    Луны, ASC, MC и домов, `chart_points`); вес, уровень, тон — шкала
    `main_event` (`day_event.score`, `feed_level`, `ASPECT_TONE`).

⚠️ Независимость от окна запроса (тест `key` в test_sky.py). Сетка
привязана к `_EPOCH`, а не к краю окна, и бисекция идёт целыми минутами от
узла сетки: один и тот же переход даёт одну и ту же минуту в любом чанке.
Проход, упёршийся в край скана, досчитывается наружу (скан растёт на
`PAD_DAYS`, как `house_periods._first_entry/_final_exit`) — иначе первое
касание петли, начатой до окна, потерялось бы и `key` зависел бы от окна.

Минута — пол момента (секунды отбрасываются), как у `_find_exact_aspect`:
минута касания входит в ключи главного события и письма.

Синхронный модуль (Swiss Ephemeris): из async — через `asyncio.to_thread`.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import NamedTuple, Optional
from zoneinfo import ZoneInfo

from backend.cache import TTL_TRANSIT, RedisCache
from backend.chart_points import _get
from backend.day_event import counts, feed_level, points, score
from backend.ephemeris.aspects import ASPECTS
from backend.ephemeris.calculator import (
    PLANETS,
    _calc_planet_position,
    _datetime_to_jd,
    _longitude_to_sign,
)
from backend.transit.engine import ASPECT_TONE, TRANSIT_ORBS, _signed
from backend.transit.house_passages import LOOP_DAYS

TRANSITS = tuple(p for p in PLANETS if p != "North Node")
# Шаг сетки, часы. Точность (минута) даёт бисекция, шаг лишь не должен быть
# длиннее прохода, иначе проход не виден: у Луны (до 15,4°/сут) проход трина
# — 3° за ~4,7 ч, поэтому 2 ч; у Солнца–Марса проход — сутки и дольше, 6 ч
# (с 4 ч чанк не укладывался в 1 с, задание 4.1).
STEP_HOURS = {"Moon": 2, "Sun": 6, "Mercury": 6, "Venus": 6, "Mars": 6}  # медленные — 24
# Запас скана за краем окна и шаг его роста, дни: больше перерыва внутри
# петли (LOOP_DAYS шага 2б) и больше одного прохода у Луны и Солнца.
PAD_DAYS = {"Moon": 2, "Sun": 6, **LOOP_DAYS}
# Дальше этого планета в перерыве петли от орба не уходит: перерыв — от
# выхода до станции и обратно, а дуга попятного хода у всех меньше 20°
# (Марс до ~20°, Венера ~16°, Меркурий ~15°, медленные < 10°).
GAP_DEG = 30
MAX_GROW = 30            # 30 × 360 дней — края не бывает
CLOSEST_MAX = 0.5        # О3
_EPOCH = datetime(2000, 1, 1, tzinfo=timezone.utc)

# v1 (05.10.2026, задание 4.1). ⚠️ Набор точек в ключ не входит, как у
# `feed:v3`: точки берутся из карты здесь же, а карта под одним id не
# меняется. Меняется расчёт — поднять версию.
sky_cache = RedisCache("sky", TTL_TRANSIT)
CACHE_VERSION = "v1"


@dataclass
class Touch:
    at_utc: datetime        # aware UTC, до минуты
    orb: float
    exact: bool             # True — корень; False — сближение без касания (О3)
    retrograde: bool
    transit_sign: str
    transit_degree: float


class SkyLocal(NamedTuple):
    start_day: date
    end_day: date
    touch_days: list[date]


@dataclass
class SkyEvent:
    key: str
    transit: str
    natal: str
    aspect: str
    start_utc: datetime                          # первый вход в орб
    end_utc: datetime                            # окончательный выход
    passes: list[tuple[datetime, datetime]]      # >1 — петля выходила из орба
    touches: list[Touch]
    closest: Touch                               # = первое касание, если оно есть
    score: float
    level: str
    tone: str                                    # ASPECT_TONE: harmonious / tense / new_cycle
    natal_sign: str
    natal_degree: float
    natal_house: Optional[int]

    def local(self, tz: str) -> SkyLocal:
        """Местные даты в поясе `tz` (имя IANA, `time_utils.user_tz`)."""
        z = ZoneInfo(tz)
        return SkyLocal(self.start_utc.astimezone(z).date(), self.end_utc.astimezone(z).date(),
                        [t.at_utc.astimezone(z).date() for t in self.touches])

    def to_dict(self) -> dict:
        d = {k: getattr(self, k) for k in self.__dataclass_fields__}
        iso = lambda t: t.isoformat()
        d.update(start_utc=iso(self.start_utc), end_utc=iso(self.end_utc),
                 passes=[[iso(a), iso(b)] for a, b in self.passes],
                 touches=[_touch_dict(t) for t in self.touches], closest=_touch_dict(self.closest))
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "SkyEvent":
        dt = datetime.fromisoformat
        return cls(**{**d, "start_utc": dt(d["start_utc"]), "end_utc": dt(d["end_utc"]),
                      "passes": [(dt(a), dt(b)) for a, b in d["passes"]],
                      "touches": [Touch(**{**t, "at_utc": dt(t["at_utc"])}) for t in d["touches"]],
                      "closest": Touch(**{**d["closest"], "at_utc": dt(d["closest"]["at_utc"])})})


def _touch_dict(t: Touch) -> dict:
    return {**t.__dict__, "at_utc": t.at_utc.isoformat()}


# ── расчёт ────────────────────────────────────────────────────────────────────

class _Track:
    """Долгота одной транзитной планеты на сетке от `_EPOCH`; узел k — момент
    `_EPOCH + k·step`. Позиция считается один раз на узел для всех точек."""

    def __init__(self, planet: str):
        self.pid = PLANETS[planet]
        self.step = timedelta(hours=STEP_HOURS.get(planet, 24))
        self.minutes = int(self.step.total_seconds() // 60)
        self._lon: dict[int, float] = {}

    def t(self, k: int) -> datetime:
        return _EPOCH + k * self.step

    def k(self, t: datetime, up: bool) -> int:
        x = (t - _EPOCH) / self.step
        return math.ceil(x) if up else math.floor(x)

    def calc(self, t: datetime) -> tuple[float, float]:
        lon, _, _, speed = _calc_planet_position(self.pid, round(_datetime_to_jd(t), 6))
        return lon, speed

    def lon(self, k: int) -> float:
        if k not in self._lon:
            self._lon[k] = self.calc(self.t(k))[0]
        return self._lon[k]

    def crossing(self, k: int, pred) -> datetime:
        """Пол момента (до минуты), где `pred` меняется между узлами k и k+1."""
        t0, p0 = self.t(k), pred(self.t(k))
        lo, hi = 0, self.minutes
        while hi - lo > 1:
            mid = (lo + hi) // 2
            lo, hi = (mid, hi) if pred(t0 + timedelta(minutes=mid)) == p0 else (lo, mid)
        return t0 + timedelta(minutes=lo)


def _series(tr: _Track, n_lon: float, ang: float, side: int, orb: float, a: int, b: int) -> list[dict]:
    """События одной стороны аспекта на узлах [a, b] — номерами узлов, без
    бисекции: проходы (`i0` — первый узел в орбе, `i1` — первый узел после;
    None — проход у края скана), склеенные по петле."""
    v = [_signed(tr.lon(k), n_lon, ang, side) for k in range(a, b + 1)]
    passes, cur = [], None
    for i, x in enumerate(v):
        if abs(x) <= orb and cur is None:
            cur = {"i0": i or None, "in": (1 if v[i - 1] > 0 else -1) if i else 0}
        elif abs(x) > orb and cur is not None:
            passes.append({**cur, "i1": i, "out": 1 if x > 0 else -1})
            cur = None
    if cur is not None:
        passes.append({**cur, "i1": None, "out": 0})
    events = []
    for p in passes:
        if events and p["in"] and p["in"] == events[-1]["out"]:
            events[-1]["passes"].append(p)
            events[-1]["out"] = p["out"]
        else:
            events.append({"passes": [p], "out": p["out"]})
    for e in events:
        e["v"], e["a"] = v, a
        # Приблизительно, по узлам: точная граница — между узлом до и узлом после.
        e["t0"] = tr.t(a + (e["passes"][0]["i0"] or 0))
        i1 = e["passes"][-1]["i1"]
        e["t1"] = tr.t(a + (len(v) - 1 if i1 is None else i1))
    return events


def _finish(tr: _Track, e: dict, f, orb: float) -> dict:
    """Минуты событий окна: входы, выходы, корни (бисекция только здесь —
    у событий запаса скана она не нужна)."""
    v, a = e["v"], e["a"]
    inside = lambda t: abs(f(t)) <= orb
    passes = [(tr.t(a) if p["i0"] is None else tr.crossing(a + p["i0"] - 1, inside),
               tr.t(a + len(v) - 1) if p["i1"] is None else tr.crossing(a + p["i1"] - 1, inside))
              for p in e["passes"]]
    lo_i, hi_i = e["passes"][0]["i0"] or 0, e["passes"][-1]["i1"] or len(v) - 1
    # |v| < 90 — смена знака у 0°, а не скачок ±180° при приведении.
    roots = [tr.crossing(a + i, lambda t: f(t) > 0) for i in range(max(lo_i - 1, 0), min(hi_i, len(v) - 1))
             if (v[i] > 0) != (v[i + 1] > 0) and abs(v[i]) < 90 and abs(v[i + 1]) < 90]
    near = a + min(range(lo_i, hi_i + 1), key=lambda i: abs(v[i]))
    return {"passes": passes, "start": passes[0][0], "end": passes[-1][1],
            "roots": [r for r in roots if passes[0][0] <= r <= passes[-1][1]], "near": near}


def _closest(tr: _Track, f, k: int) -> datetime:
    """Минимум |f| возле узла k (станция): тернарный поиск целыми минутами."""
    lo, hi = tr.t(k) - tr.step, tr.t(k) + tr.step
    while hi - lo > timedelta(minutes=2):
        m1, m2 = lo + (hi - lo) / 3, hi - (hi - lo) / 3
        lo, hi = (lo, m2) if abs(f(m1)) <= abs(f(m2)) else (m1, hi)
    return (lo + (hi - lo) / 2).replace(second=0, microsecond=0)


def _touch(tr: _Track, f, at: datetime, exact: bool) -> Touch:
    lon, speed = tr.calc(at)
    sign, deg = _longitude_to_sign(lon)
    return Touch(at, round(abs(f(at)), 4), exact, speed < 0, sign, round(deg, 2))


def _planet_events(planet: str, pts: list[dict], lo: datetime, hi: datetime) -> list[SkyEvent]:
    tr = _Track(planet)
    pad = timedelta(days=PAD_DAYS[planet])
    pad_k = math.ceil(pad / tr.step)
    ka, kb = tr.k(lo, False), tr.k(hi, True)
    out = []
    for p in pts:
        n_sign, n_deg = _longitude_to_sign(p["longitude"])
        for asp, ang in ASPECTS.items():
            if not counts(p["name"], asp):
                continue
            orb = TRANSIT_ORBS[asp]
            for side in ((1,) if ang in (0, 180) else (1, -1)):
                n = p["longitude"]
                # Планета за окно не подходит к точке ближе GAP_DEG — событий,
                # пересекающих окно, нет (даже перерыва петли).
                if all(abs(_signed(tr.lon(k), n, ang, side)) > orb + GAP_DEG for k in range(ka, kb + 1)):
                    continue
                a, b = ka - pad_k, kb + pad_k
                for _ in range(MAX_GROW):
                    evs = [e for e in _series(tr, n, ang, side, orb, a, b)
                           if e["t1"] >= lo and e["t0"] - tr.step <= hi]
                    # Событие окна начинается ближе запаса к краю скана — до
                    # края мог быть его проход (петля): скан растёт наружу.
                    grow_a = any(e["t0"] < tr.t(a) + pad for e in evs)
                    grow_b = any(e["t1"] > tr.t(b) - pad for e in evs)
                    if not (grow_a or grow_b):
                        break
                    a -= grow_a * pad_k
                    b += grow_b * pad_k
                f = lambda t, n=n, ang=ang, side=side: _signed(tr.calc(t)[0], n, ang, side)
                for e in (_finish(tr, e, f, orb) for e in evs):
                    if e["end"] < lo or e["start"] > hi:
                        continue
                    touches = [_touch(tr, f, t, True) for t in e["roots"]]
                    if touches:
                        closest = touches[0]
                    else:
                        closest = _touch(tr, f, _closest(tr, f, e["near"]), False)
                        if closest.orb > CLOSEST_MAX:
                            continue
                    out.append(SkyEvent(
                        key=f"{planet}:{p['name']}:{asp}:{closest.at_utc.date().isoformat()}",
                        transit=planet, natal=p["name"], aspect=asp,
                        start_utc=e["start"], end_utc=e["end"], passes=e["passes"],
                        touches=touches, closest=closest,
                        score=score(planet, p["name"], asp), level=feed_level(planet, p["name"], asp),
                        tone=ASPECT_TONE[asp], natal_sign=n_sign, natal_degree=round(n_deg, 2),
                        natal_house=p.get("house"),
                    ))
    return out


def compute(chart, from_utc: datetime, to_utc: datetime) -> list[SkyEvent]:
    """События, пересекающие [from_utc, to_utc], без кэша."""
    pts = points(chart)
    return [e for planet in TRANSITS for e in _planet_events(planet, pts, from_utc, to_utc)]


def _months(from_utc: datetime, to_utc: datetime) -> list[tuple[int, int]]:
    y, m, out = from_utc.year, from_utc.month, []
    while (y, m) <= (to_utc.year, to_utc.month):
        out.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def _chunk(chart, y: int, m: int) -> list[SkyEvent]:
    """События, пересекающие UTC-месяц. Чанк — по месяцу пересечения, а не
    якоря: событие Плутона длится до трёх лет, и по якорю окно в месяц
    пришлось бы собирать из трёх лет чанков. Долгое событие лежит в
    нескольких чанках одинаковым (`key` от окна не зависит)."""
    lo = datetime(y, m, 1, tzinfo=timezone.utc)
    hi = datetime(y + m // 12, m % 12 + 1, 1, tzinfo=timezone.utc) - timedelta(minutes=1)
    chart_id = _get(chart, "id")
    key = f"{CACHE_VERSION}:{chart_id}:{y:04d}-{m:02d}"
    if chart_id is not None:
        cached = sky_cache.get(key)
        if cached is not None:
            return [SkyEvent.from_dict(d) for d in cached]
    events = compute(chart, lo, hi)
    if chart_id is not None:
        # Живёт до конца следующего месяца: месяц M нужен и как «прошлый»
        # (местные сутки 1-го числа начинаются в UTC ещё в M−1). Раньше не
        # истекает — иначе между прогревами холодный расчёт попал бы в запрос.
        until = datetime(y + (m + 1) // 12, (m + 1) % 12 + 1, 1, tzinfo=timezone.utc) + timedelta(days=1)
        ttl = max(int((until - datetime.now(timezone.utc)).total_seconds()), 86400)
        sky_cache.set(key, [e.to_dict() for e in events], ttl=ttl)
    return events


def sky_events(chart, from_utc: datetime, to_utc: datetime) -> list[SkyEvent]:
    """События, пересекающие [from_utc, to_utc] (aware UTC), из чанков
    `sky:v1:{chart}:{YYYY-MM}`; по началу, затем по ключу."""
    seen: dict[str, SkyEvent] = {}
    for y, m in _months(from_utc, to_utc):
        for e in _chunk(chart, y, m):
            if e.end_utc >= from_utc and e.start_utc <= to_utc:
                seen.setdefault(e.key, e)
    return sorted(seen.values(), key=lambda e: (e.start_utc, e.key))


# ── Разбор транзита (задание 4.5) ─────────────────────────────────────────────

def find_event(chart, transit: str, natal: str, aspect: str, on: date) -> SkyEvent | None:
    """Событие, которое открывает карточка с `peak_date = on` (UTC-дата).

    Сначала — событие с касанием в ±1 день от `on`: карточка ленты под флагом
    шлёт UTC-дату касания, старая лента и веб (`/transits` до 4.8) — дату пика
    движка, она с касанием расходится не больше чем на сутки. Нет такого —
    событие, идущее в этот день (веб мог прислать станцию без касания).
    None — события у ядра нет, разбор идёт старым путём."""
    s = datetime(on.year, on.month, on.day, tzinfo=timezone.utc)
    cands = [e for e in sky_events(chart, s - timedelta(days=1), s + timedelta(days=2))
             if (e.transit, e.natal, e.aspect) == (transit, natal, aspect)]
    near = [e for e in cands if any(abs((t.at_utc.date() - on).days) <= 1 for t in e.touches)]
    return (near or [e for e in cands if e.start_utc < s + timedelta(days=1) and e.end_utc >= s] or [None])[0]


def interpret_facts(ev: SkyEvent, tz: str, cusps: list[float] | None) -> dict:
    """Факты разбора из события ядра: те же поля, что у
    `engine.compute_exact_facts`, плюс все касания и перерывы петли.

    Один разбор на событие (О5), поэтому положение транзитной планеты, орб и
    «ретроградный» — на ПЕРВОМ касании (`closest`), а не на касании карточки:
    иначе текст зависел бы от того, с какой карточки его открыли. Даты —
    местные в поясе `tz`. `gaps` — перерывы петли (вне орба), местные даты
    выхода и возврата; в промпт пока не идут (формулировка ждёт владельца)."""
    from backend.ephemeris.calculator import ZODIAC_SIGNS, _find_house
    z = ZoneInfo(tz)
    d = lambda t: t.astimezone(z).date().isoformat()
    c = ev.closest
    lon = ZODIAC_SIGNS.index(c.transit_sign) * 30 + c.transit_degree
    return {
        "transit_sign": c.transit_sign, "transit_degree": c.transit_degree,
        "transit_house": _find_house(lon, cusps) if cusps else None,
        "transit_retrograde": c.retrograde,
        "natal_sign": ev.natal_sign, "natal_degree": ev.natal_degree, "natal_house": ev.natal_house,
        "exact_orb": round(c.orb, 2),
        "exact_date": d(ev.touches[0].at_utc) if ev.touches else None,
        "exact_dates": [d(t.at_utc) for t in ev.touches],
        "period_start": d(ev.start_utc), "period_end": d(ev.end_utc),
        "gaps": [(d(a[1]), d(b[0])) for a, b in zip(ev.passes, ev.passes[1:])],
    }


# ── Прогрев (задание 4.2) ─────────────────────────────────────────────────────
# Холодный чанк — около секунды, год — 15 с: в запрос человека (виджет,
# прогноз, сторис) это попадать не должно. Прогрев — `tasks.sky_warm`: beat
# ежечасно для всех карт под флагом `sky_event` и сразу после сохранения
# карты (`calculate`, `claim`). Считаются только недостающие чанки.

def warm_chart(chart, now: datetime | None = None) -> None:
    """Чанки прошлого, текущего и следующего UTC-месяца."""
    now = now or datetime.now(timezone.utc)
    first = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    sky_events(chart, first - timedelta(days=1), first + timedelta(days=62))


def warm(db, chart_id: str | None = None) -> int:
    """Прогреть карты, у владельцев которых флаг `sky_event` включён."""
    from backend.day_event import SKY_FLAG
    from backend.flags import flag_on
    from backend.models import NatalChart
    q = db.query(NatalChart)
    if chart_id:
        q = q.filter(NatalChart.id == chart_id)
    n = 0
    for chart in q.yield_per(100):
        if chart.planets and flag_on(db, SKY_FLAG, chart.user_id):
            warm_chart(chart)
            n += 1
    return n
