"""backend/feed/builder.py — сборка ленты событий из трёх существующих источников.

Лента — это НЕ новый расчёт. Транзиты, периоды планера и лунные события
считаются теми же функциями, что и для /transits, /planner/monthly и
/calendar/lunar; здесь они только приводятся к одному виду: одно время, один
ключ, одна шкала важности.

Три вещи, которые здесь решены и которые нельзя «упростить» обратно.


1. МЕСЯЧНАЯ СЕТКА ТРАНЗИТОВ — из-за неё ключи вообще возможны

`calculate_transits` ищет пик аспекта ВНУТРИ переданного диапазона. Если
настоящий пик лежит за краем — вернётся ближайшее сближение у границы, с
другой датой и другим орбом. Проверено боем на трёх перекрывающихся окнах
(FEED_API_RECON_2026-09-04.md): из 31 транзита, попавшего во все три окна,
`peak_date` разошёлся у 4, `peak_orb` — у тех же 4, `start_date` — у 9.
Пример: Юпитер в квадрате к Плутону — 2026-09-03/09-09/09-09 и орб
1.1107/0.0117/0.0117.

Поэтому окно пользователя НЕ передаётся движку. Транзиты считаются
помесячно: для каждого календарного месяца, пересекающего запрос, скан идёт
по [начало месяца − PAD, конец месяца + PAD], и оставляются только события,
чей пик попал внутрь самого месяца. Диапазон скана зависит только от
(карта, год, месяц) — не от окна, — поэтому пик у события всегда настоящий:
он лежит строго внутри просканированного отрезка, а не у его границы.
Событие принадлежит ровно одному месяцу, дублей на стыке нет.

Побочно это дешевле: месяц ≈ 40 дней скана вместо 366 в худшем случае,
и чанк переиспользуется между запросами (см. п. 3).


2. ВРЕМЯ — одна конвертация на всю ленту

Наружу каждое событие уходит с ISO-временем и явным смещением, в таймзоне
карты. Внутри всё сводится к aware-datetime в UTC и переводится один раз.
Ни одного «+3» в этом файле нет и быть не должно: именно так разъехались
затмения (UTC) и фазы Луны (GMT+3) в /calendar/lunar — находка 3.7 CLAUDE.md.


3. КЭШ — Redis с in-memory запасом, инвалидация не нужна

Чанк месяца кладётся в RedisCache (префикс `feed`, TTL 7 суток — тот же
класс данных, что у transit_cache: посчитанные эфемериды, которые сами по
себе не устаревают). При недоступном Redis RedisCache молча падает на
словарь в памяти процесса — тогда кэш у каждого процесса свой, и это
нормально: он ускоряет, а не хранит истину.

Инвалидации по карте нет намеренно. Астрономические поля карты не правит ни
одна ручка — проверено grep'ом по backend: присваивания chart.planets и
подобных есть только в тестах. Пересчёт карты создаёт НОВУЮ строку с новым
id (POST /chart/calculate всегда вставляет), то есть и новый ключ кэша.
Ключ содержит версию `v1` — если поменяется сам расчёт, версия поднимается
и старые чанки перестают читаться, без ручной чистки Redis.
"""

from __future__ import annotations

import calendar as _calendar
import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import pytz

from backend.cache import RedisCache, TTL_TRANSIT
from backend.calendar.lunar_engine import jd_to_utc
from backend.feed.horizon import feed_horizon

# Скан месяца расширяется на столько суток в каждую сторону. Нужен только для
# того, чтобы пик события, лежащего внутри месяца, не оказался НА границе
# скана: пик ищется по сетке шагов, и у самого края движок вернёт край. Пяти
# суток хватает с запасом — событию, чей пик внутри месяца, до края скана
# всегда не меньше PAD. Границы прохода (start/end) при этом всё равно могут
# быть обрезаны, но лента их не отдаёт (см. _transit_events).
SCAN_PAD_DAYS = 5

# Транзиты Луны — три четверти ленты (114 событий из 160 за август на
# разведочной карте). Отдельный уровень важности заведён ровно под них.
_LOW_IMPORTANCE_TRANSIT_PLANETS = {"Moon"}

feed_cache = RedisCache("feed", TTL_TRANSIT)

_TEMPLATES_PATH = Path(__file__).parent / "templates.json"
with open(_TEMPLATES_PATH, encoding="utf-8") as _f:
    TEMPLATES: dict = json.load(_f)


# ── Важность ─────────────────────────────────────────────────────────────────

IMPORTANCE_HIGH = "high"
IMPORTANCE_MEDIUM = "medium"
IMPORTANCE_LOW = "low"


# ── Ключи ────────────────────────────────────────────────────────────────────

def _key(prefix: str, *parts: Any) -> str:
    """Детерминированный ключ события.

    Строится только из полей, которые НЕ зависят от запрошенного окна.
    Для транзита это (карта, транзитная планета, натальная точка, аспект,
    дата пика), где дата пика получена на месячной сетке — см. шапку модуля.
    Хеш, а не склейка: ключ уходит на клиент, и по нему не должно читаться
    ни имя карты, ни её id.

    sha256, обрезанный до 16 символов, — та же конвенция, что у
    make_profile_hash (cache.py). Не sha1: bandit помечает его B324 как
    слабый, и глушить предупреждение `usedforsecurity=False` ради экономии,
    которой здесь нет, — плохой размен. Идентификатор от смены алгоритма не
    страдает, а лишнего исключения в security-прогоне не появляется.
    """
    raw = "|".join(str(p) for p in parts)
    return f"{prefix}:{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]}"


# ── Время ────────────────────────────────────────────────────────────────────

def _tz(timezone_name: Optional[str]) -> Any:
    """Таймзона карты. UTC — запасной вариант, а не умолчание: карта без
    таймзоны означает, что геокодер её не отдал, и это редкий случай."""
    if not timezone_name:
        return pytz.UTC
    try:
        return pytz.timezone(timezone_name)
    except Exception:
        return pytz.UTC


def _to_local_iso(dt_utc: datetime, tz) -> str:
    """Aware-UTC → ISO со смещением в таймзоне карты.

    Микросекунды отбрасываются: движок домов отдаёт границы периодов с
    точностью до микросекунды («05:03:32.001801»), и это шум бисекции, а не
    астрономия. В ленте они мешали бы и глазу, и сравнению ключей.
    """
    return dt_utc.astimezone(tz).replace(microsecond=0).isoformat()


def _naive_utc_to_local_iso(naive: datetime, tz) -> str:
    """Наивный UTC-datetime (так их отдают движки транзитов и домов) → ISO.

    Движки считают в UTC и возвращают datetime без tzinfo. Пометить их
    UTC — единственное место, где это знание применяется.
    """
    return _to_local_iso(pytz.UTC.localize(naive), tz)


# ── Шаблонный текст ──────────────────────────────────────────────────────────

def transit_text(transit_planet: str, natal_planet: str, aspect_type: str) -> Optional[str]:
    """Заголовок транзита из templates.json. Ни ИИ, ни квоты.

    Собирается ровно как строка `key` в LockedTransitPanel на вебе
    (TransitTimeline.jsx): «Уран Соединение Меркурий». Бесплатный пользователь
    уже видит эту подпись на ChartPage — лента показывает ту же.

    None возвращается, только если в файле нет какой-то из трёх частей: тогда
    подписи не будет вовсе, и это заметно, а не молча подставленная заглушка.
    """
    aspect = TEMPLATES.get("aspects", {}).get(aspect_type, "")
    transit = TEMPLATES.get("transit_planets", {}).get(transit_planet, "")
    natal = TEMPLATES.get("natal_labels", {}).get(natal_planet, "")
    if not (aspect and transit and natal):
        return None
    return (
        TEMPLATES.get("pattern", "{transit} {aspect} {natal}")
        .replace("{transit}", transit)
        .replace("{aspect}", aspect)
        .replace("{natal}", natal)
    )


def transit_teaser(tier: Optional[str], free_unlocked: bool) -> Optional[dict]:
    """Подводка вместо разбора — то же, что показывает веб бесплатному.

    Возвращается только тем, кому разбор недоступен. Условие взято с фронта
    (TransitTimeline.jsx, isEventVisible): на lite и выше разбор открыт всегда,
    на free — только у топ-2 значимых транзитов (`free_unlocked`).

    ⚠️ Сам разбор лента не отдаёт и квоту не считает — это следующее задание.
    Здесь только текст-заглушка, чтобы бесплатный пользователь видел в ленте
    то же, что уже видит на сайте, а не пустое место.
    """
    if tier in ("lite", "pro", "premium") or free_unlocked:
        return None
    return TEMPLATES.get("teaser", {}).get("free") or None


# ── Транзиты ─────────────────────────────────────────────────────────────────

def _months_between(from_date: date, to_date: date) -> list[tuple[int, int]]:
    """Календарные месяцы, пересекающие окно, по возрастанию."""
    out: list[tuple[int, int]] = []
    y, m = from_date.year, from_date.month
    while (y, m) <= (to_date.year, to_date.month):
        out.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def _transit_chunk(chart_id: str, natal_planets: list[dict], year: int, month: int) -> list[dict]:
    """Транзиты, чей ПИК приходится на указанный календарный месяц.

    Единица кэширования и единственное место, где зовётся движок транзитов.
    """
    cache_key = f"v1:{chart_id}:{year:04d}-{month:02d}"
    cached = feed_cache.get(cache_key)
    if cached is not None:
        return cached

    from backend.transit.engine import calculate_transits, mark_transit_significance

    last_day = _calendar.monthrange(year, month)[1]
    month_start = date(year, month, 1)
    month_end = date(year, month, last_day)

    events = calculate_transits(
        natal_planets=natal_planets,
        from_date=month_start - timedelta(days=SCAN_PAD_DAYS),
        to_date=month_end + timedelta(days=SCAN_PAD_DAYS),
    )
    mark_transit_significance(events)

    chunk = [
        {
            "transit_planet": e.transit_planet,
            "natal_planet": e.natal_planet,
            "aspect_type": e.aspect_type,
            "transit_sign": e.transit_sign,
            "transit_degree": e.transit_degree,
            "natal_sign": e.natal_sign,
            "peak_date": e.peak_date,
            "exact_date": e.exact_date,
            "peak_orb": e.peak_orb,
            "applying": e.applying,
            "significant": e.significant,
            # ⚠️ Семантика ОТЛИЧАЕТСЯ от /transits, и это осознанно.
            # mark_transit_significance открывает топ-2 значимых по орбу
            # ВНУТРИ переданного списка. У /transits список — запрошенное окно,
            # поэтому там топ-2 меняются, стоит пролистать таймлайн. Здесь
            # список — календарный месяц, то есть топ-2 фиксированы на месяц и
            # не зависят от окна, как и всё остальное в ленте.
            # Разбор по этому флагу лента пока не открывает (это следующее
            # задание) — флаг нужен подводке, см. transit_teaser.
            "free_unlocked": e.free_unlocked,
        }
        for e in events
        # Пик внутри самого месяца, без PAD: PAD нужен движку, а не выдаче.
        # Так событие попадает ровно в один чанк и не двоится на стыке.
        if month_start.isoformat() <= e.peak_date <= month_end.isoformat()
    ]
    feed_cache.set(cache_key, chunk)
    return chunk


def _transit_events(chart_id: str, natal_planets: list[dict],
                    from_date: date, to_date: date, tz, tier: Optional[str]) -> list[dict]:
    out: list[dict] = []
    for year, month in _months_between(from_date, to_date):
        for e in _transit_chunk(chart_id, natal_planets, year, month):
            peak = date.fromisoformat(e["peak_date"])
            if not (from_date <= peak <= to_date):
                continue

            # exact_date — момент пика с точностью до минуты, наивный UTC.
            # Если его нет (движок отдаёт Optional), берём полдень дня пика:
            # лента сортируется по времени, и событие без времени провалилось
            # бы в начало суток вперёд всех остальных.
            if e.get("exact_date"):
                at_utc_naive = datetime.fromisoformat(e["exact_date"])
            else:
                at_utc_naive = datetime.combine(peak, datetime.min.time()) + timedelta(hours=12)

            if e["transit_planet"] in _LOW_IMPORTANCE_TRANSIT_PLANETS:
                importance = IMPORTANCE_LOW
            elif e["significant"]:
                importance = IMPORTANCE_HIGH
            else:
                importance = IMPORTANCE_MEDIUM

            out.append({
                "key": _key("t", chart_id, e["transit_planet"],
                            e["natal_planet"], e["aspect_type"], e["peak_date"]),
                "kind": "transit",
                "importance": importance,
                # Транзит — точка на оси, по peak_date (решение владельца).
                # start_date и end_date не отдаются ВООБЩЕ: оба обрезаются
                # окном запроса без всякой пометки (start расходится у 9 из 31
                # событий, end — у 7), то есть показывать их как «начало» и
                # «конец» транзита нельзя. Длительности у транзита в ленте нет.
                "at": _naive_utc_to_local_iso(at_utc_naive, tz),
                "ends_at": None,
                "duration_days": None,
                # Транзит в ленте не заперт: сам список транзитов открыт всем
                # тарифам — на free с горизонтом 3 месяца
                # (FREE_TRANSITS_TEASER_MONTHS, main.py явно НЕ подключает
                # check_transit_access, чтобы не закрыть витрину). Платный там
                # только AI-разбор, а его лента не отдаёт вовсе.
                "locked": False,
                "text": transit_text(e["transit_planet"], e["natal_planet"], e["aspect_type"]),
                "teaser": transit_teaser(tier, e["free_unlocked"]),
                "meta": {
                    "transit_planet": e["transit_planet"],
                    "transit_sign": e["transit_sign"],
                    "transit_degree": e["transit_degree"],
                    "natal_planet": e["natal_planet"],
                    "natal_sign": e["natal_sign"],
                    "aspect_type": e["aspect_type"],
                    "peak_orb": e["peak_orb"],
                    "applying": e["applying"],
                    "significant": e["significant"],
                    "free_unlocked": e["free_unlocked"],
                },
            })
    return out


# ── Планер ───────────────────────────────────────────────────────────────────

def _planner_events(chart_id: str, natal_profile: dict, from_date: date, to_date: date,
                    today: date, timezone_name: Optional[str], tier: Optional[str], tz) -> list[dict]:
    """Периоды планера с настоящими ISO-датами.

    Границы берутся из start_dt/end_dt, которые compute_planner_periods кладёт
    рядом со строкой `period`. Строка вида «07.08 — 06.09» не парсится: у неё
    нет года, и его пришлось бы доставать из заголовка месяца — ровно та
    хрупкость, ради устранения которой лента и заводится.

    month_offset наружу не протекает: сюда приходят обычные даты, а
    compute_planner_periods принимает from_date/to_date напрямую.
    """
    from backend.transit.house_passages import compute_planner_periods
    from backend.transit.planner_engine import (
        _KEY_TO_ENG,
        _locked_payload,
        _unlocked_payload,
        is_longterm_locked,
        is_month_period_locked,
        is_moon_week_locked,
    )

    periods = compute_planner_periods(
        natal_profile=natal_profile,
        from_date=from_date,
        to_date=to_date,
        today=today,
        user_timezone=timezone_name,
    )

    out: list[dict] = []

    def add(kind: str, planet_key: str, planet_name: str, emoji: str,
            house: int, start_iso: str, end_iso: str, locked: bool, eng: str) -> None:
        start_dt = datetime.fromisoformat(start_iso)
        end_dt = datetime.fromisoformat(end_iso)
        payload = _locked_payload() if (locked or not house) else _unlocked_payload(eng, house)
        out.append({
            "key": _key("p", chart_id, planet_key, house, start_iso, end_iso),
            "kind": kind,
            "importance": IMPORTANCE_MEDIUM,
            "at": _naive_utc_to_local_iso(start_dt, tz) if start_dt.tzinfo is None
                  else _to_local_iso(start_dt, tz),
            "ends_at": _naive_utc_to_local_iso(end_dt, tz) if end_dt.tzinfo is None
                       else _to_local_iso(end_dt, tz),
            # Длительность в сутках — по просьбе владельца: долгосрочный
            # транзит идёт месяцами (в разведке был период 14.07.2025 —
            # 05.09.2026) и в ленте, листаемой по дням, присутствует в каждом
            # окне. По этому числу фронт сам решает, как его рисовать; отдельной
            # сущности под «длинный период» не заводится.
            "duration_days": (end_dt.date() - start_dt.date()).days,
            "locked": locked,
            "text": None,
            "teaser": None,
            "meta": {
                "planet": planet_key,
                "planet_name": planet_name,
                "emoji": emoji,
                "house": house,
                **payload,
            },
        })

    for p in periods.get("fast_planets", []):
        eng = _KEY_TO_ENG.get(p["planet_key"], "")
        for period in p.get("periods", []):
            house = period.get("house")
            if not house or not period.get("start_dt"):
                continue
            add("planner_period", p["planet_key"], p["planet_name"], p["emoji"], house,
                period["start_dt"], period["end_dt"],
                is_month_period_locked(tier, p["planet_key"], period.get("is_current", False)),
                eng)

    for p in periods.get("moon_week", []):
        house = p.get("house")
        if not house or not p.get("start_dt"):
            continue
        add("planner_moon_house", "moon", "Луна", "🌙", house,
            p["start_dt"], p["end_dt"], is_moon_week_locked(tier), "Moon")

    for p in periods.get("slow_planets", []):
        house = p.get("house")
        if not house or not p.get("start_dt"):
            continue
        add("planner_longterm", p["planet_key"], p["planet_name"], p["emoji"], house,
            p["start_dt"], p["end_dt"], is_longterm_locked(tier),
            _KEY_TO_ENG.get(p["planet_key"], ""))

    # Ретроградные станции — точечные события планера. locked у них нет вовсе,
    # они отдаются всем тарифам как есть (см. FEED_API_RECON, раздел планера).
    for r in periods.get("retrogrades", []):
        # `date` здесь — строка «дд.мм» без года: единственное место планера,
        # где настоящей даты нет. Год восстанавливается по окну, а не по
        # заголовку: станция всегда внутри запрошенного диапазона, потому что
        # compute_retrograde_stations сканирует ровно его.
        try:
            day, mon = (int(x) for x in r["date"].split("."))
        except Exception:
            continue
        year = from_date.year if (mon, day) >= (from_date.month, from_date.day) else to_date.year
        try:
            station = date(year, mon, day)
        except ValueError:
            continue
        at = datetime.combine(station, datetime.min.time()) + timedelta(hours=12)
        out.append({
            "key": _key("r", chart_id, r["planet"], r["status"], station.isoformat()),
            "kind": "retrograde",
            "importance": IMPORTANCE_MEDIUM,
            "at": _naive_utc_to_local_iso(at, tz),
            "ends_at": None,
            "duration_days": None,
            "locked": False,
            "text": r.get("label"),
            "teaser": None,
            "meta": {"planet": r.get("planet"), "planet_name": r.get("planet_name"),
                     "status": r.get("status")},
        })

    return out


# ── Лунные события ───────────────────────────────────────────────────────────

def _lunar_events(from_date: date, to_date: date, tz) -> list[dict]:
    """Фазы, затмения, равноденствия и солнцестояния.

    Момент у всех трёх берётся из jd_to_utc — одной функции, а не трёх разных
    форматтеров, как это было до ленты. daily_signs сюда не попадают
    намеренно: это не событие, а фон дня (30 записей на месяц), в ленту
    событий он не ложится — решение владельца 04.09.2026.
    """
    from backend.calendar.lunar_engine import (
        _jd, _find_phase, _lon, _sign, PLANET_IDS,
        _scan_eclipses, _SOLAR_KIND_FLAGS, _LUNAR_KIND_FLAGS, SOLAR_EVENTS,
    )
    import swisseph as swe

    out: list[dict] = []
    jd_start = _jd(from_date, 0.0)
    jd_end = _jd(to_date, 24.0)

    # Фазы: те же две цели, что и в /calendar/lunar (0° — новолуние, 180° —
    # полнолуние), тем же _find_phase. Здесь не фильтруется по месяцу — окно
    # ленты произвольное.
    #
    # Момент (`_at_utc`) держится рядом с готовым словарём, а не только внутри
    # него: он нужен ниже для сверки с затмением по РЕАЛЬНОМУ времени, а не по
    # календарной дате — см. _ECLIPSE_PHASE_MERGE_HOURS. Наружу это поле не
    # уходит, срезается перед тем, как список попадёт в `out`.
    phase_events: list[dict] = []
    for target, etype, emoji, label in (
        (0.0, "new_moon", "🌑", "Новолуние"),
        (180.0, "full_moon", "🌕", "Полнолуние"),
    ):
        # Отсечение фантомных фаз (ложное пересечение на противоположной точке
        # орбиты) живёт ВНУТРИ _find_phase — там же, где и возникает. Здесь
        # его копии нет намеренно: одна проверка на проект, а не по одной у
        # каждого потребителя. Подробности — докстринг _find_phase.
        for jd in _find_phase(jd_start, jd_end, target):
            at_utc = jd_to_utc(jd)
            moon_lon, _ = swe.calc_ut(jd, swe.MOON, swe.FLG_SWIEPH)
            sign = _sign(moon_lon[0])
            phase_events.append({
                "_at_utc": at_utc,
                "key": _key("l", etype, at_utc.isoformat()),
                "kind": "moon_phase",
                "importance": IMPORTANCE_MEDIUM,
                "at": _to_local_iso(at_utc, tz),
                "ends_at": None,
                "duration_days": None,
                "locked": False,
                "text": f"{label} в {sign}",
                "teaser": None,
                "meta": {"type": etype, "emoji": emoji, "sign": sign},
            })

    # Затмения — единственный вид, приходивший в /calendar/lunar в UTC, когда
    # всё остальное шло в GMT+3. Здесь разницы нет: зона одна на всю ленту.
    eclipses = (
        _scan_eclipses(jd_start, jd_end, swe.sol_eclipse_when_glob, _SOLAR_KIND_FLAGS, "solar")
        + _scan_eclipses(jd_start, jd_end, swe.lun_eclipse_when, _LUNAR_KIND_FLAGS, "lunar")
    )
    eclipse_events: list[dict] = []
    for ec in eclipses:
        at_utc = datetime.fromisoformat(f"{ec.date}T{ec.time.split()[0]}:00").replace(tzinfo=pytz.UTC)
        eclipse_events.append({
            "_at_utc": at_utc,
            "_phase_type": _ECLIPSE_TO_PHASE_TYPE.get(ec.type),
            "key": _key("l", "eclipse", ec.type, ec.kind, at_utc.isoformat()),
            "kind": "eclipse",
            "importance": IMPORTANCE_HIGH,
            "at": _to_local_iso(at_utc, tz),
            "ends_at": None,
            "duration_days": None,
            "locked": False,
            # У затмения в /calendar/lunar нет ни description, ни emoji — только
            # type и kind (набор полей у него меньше, чем у фазы). Подпись
            # собирается здесь, иначе фронту пришлось бы делать это самому.
            "text": _ECLIPSE_LABELS.get((ec.type, ec.kind), "Затмение"),
            "teaser": None,
            "meta": {"type": ec.type, "kind": ec.kind},
        })

    # Затмение — это фаза: солнечное происходит только в новолуние, лунное —
    # только в полнолуние (проверено исполнением на боевых данных, 05.09.2026,
    # FEED_DUPLICATE_MOMENTS.md — 7 затмений из 7 сопровождались фазой того же
    # рода). Показывать оба — значит показать один момент дважды под разными
    # подписями: «Новолуние в Деве» и «Полное солнечное затмение» с разницей в
    # минуты. Решение владельца: фаза не отдаётся, если рядом есть затмение
    # того же рода, а знак зодиака (у затмения его в данных нет) переезжает в
    # карточку затмения — иначе это содержание терялось бы вместе с фазой.
    #
    # ⚠️ Порог — часы, а не сравнение календарных дат. Лента показывает время
    # в таймзоне карты; пара, разошедшаяся на 19 минут (наблюдавшийся максимум
    # на боевых данных) вокруг полуночи по местному времени, оказалась бы на
    # РАЗНЫХ календарных днях, хотя по факту — один и тот же момент. Три часа —
    # это наблюдавшийся максимум (19 минут) с запасом на порядок, а не подгонка
    # под конкретную пару.
    suppressed_phase_keys: set[str] = set()
    for ec in eclipse_events:
        if ec["_phase_type"] is None:
            continue  # неизвестный тип затмения — сверять не с чем
        match = min(
            (p for p in phase_events if p["meta"]["type"] == ec["_phase_type"]),
            key=lambda p: abs((p["_at_utc"] - ec["_at_utc"]).total_seconds()),
            default=None,
        )
        if match is None:
            continue
        if abs((match["_at_utc"] - ec["_at_utc"]).total_seconds()) <= _ECLIPSE_PHASE_MERGE_HOURS * 3600:
            suppressed_phase_keys.add(match["key"])
            ec["meta"]["sign"] = match["meta"]["sign"]

    for p in phase_events:
        if p["key"] in suppressed_phase_keys:
            continue
        del p["_at_utc"]
        out.append(p)

    for ec in eclipse_events:
        del ec["_at_utc"]
        del ec["_phase_type"]
        out.append(ec)

    # Равноденствия и солнцестояния: та же математика, что в get_solar_events,
    # но без привязки к календарному месяцу — окно ленты произвольное.
    for target, etype, emoji, label in SOLAR_EVENTS:
        step, jd, prev = 1.0, jd_start - 1, None
        while jd <= jd_end + 1:
            val = (_lon(jd, "Sun") - target + 180) % 360 - 180
            if prev is not None and prev < 0 <= val:
                lo, hi = jd - step, jd
                for _ in range(48):
                    mid = (lo + hi) / 2
                    if ((_lon(mid, "Sun") - target + 180) % 360 - 180) < 0:
                        lo = mid
                    else:
                        hi = mid
                at_utc = jd_to_utc((lo + hi) / 2)
                if jd_start <= (lo + hi) / 2 <= jd_end:
                    out.append({
                        "key": _key("l", etype, at_utc.isoformat()),
                        "kind": "solar_event",
                        "importance": IMPORTANCE_MEDIUM,
                        "at": _to_local_iso(at_utc, tz),
                        "ends_at": None,
                        "duration_days": None,
                        "locked": False,
                        "text": label,
                        "teaser": None,
                        "meta": {"type": etype, "emoji": emoji},
                    })
            prev = val
            jd += step

    return out


_ECLIPSE_LABELS = {
    ("solar", "total"): "Полное солнечное затмение",
    ("solar", "annular"): "Кольцеобразное солнечное затмение",
    ("solar", "partial"): "Частное солнечное затмение",
    ("lunar", "total"): "Полное лунное затмение",
    ("lunar", "partial"): "Частное лунное затмение",
    ("lunar", "penumbral"): "Полутеневое лунное затмение",
}

# Затмение — это фаза: солнечное бывает только в новолуние, лунное — только в
# полнолуние. См. дедупликацию в _lunar_events.
_ECLIPSE_TO_PHASE_TYPE = {"solar": "new_moon", "lunar": "full_moon"}

# Порог сверки затмения с фазой — часы, не календарная дата (см. комментарий
# в _lunar_events). Наблюдавшийся максимум на боевых данных — 19 минут.
_ECLIPSE_PHASE_MERGE_HOURS = 3


# ── Сборка ───────────────────────────────────────────────────────────────────

def build_feed(*, chart, from_date: date, to_date: date, today: date,
               tier: Optional[str]) -> dict:
    """Лента событий за произвольное окно. Одна зона, одна сортировка.

    Окно обрезается горизонтом ДО расчёта — один раз, для всех трёх
    источников сразу. Именно здесь, а не в роутере: иначе лунные события,
    у которых своего тарифного гейта нет вовсе, торчали бы за краем
    транзитов. Подробности — backend/feed/horizon.py.
    """
    tz = _tz(getattr(chart, "timezone", None))
    chart_id = str(chart.id)

    horizon = feed_horizon(tier, today)
    eff_from, eff_to = horizon.clamp(from_date, to_date)

    # Окно целиком за горизонтом — событий нет, но ответ не пустой: в нём
    # граница и следующий тариф, чтобы фронту было чем нарисовать край.
    if eff_from > eff_to:
        return {
            "chart_id": chart_id,
            "from_date": from_date.isoformat(),
            "to_date": to_date.isoformat(),
            "timezone": str(tz),
            "horizon": horizon.to_dict(),
            "events": [],
        }

    from_date, to_date = eff_from, eff_to

    events = _transit_events(chart_id, chart.planets, from_date, to_date, tz, tier)
    events += _lunar_events(from_date, to_date, tz)

    # Планер требует домов, а они есть только при известном времени рождения.
    # Ручка /planner/monthly в этом случае отдаёт объект с error; лента просто
    # не показывает периодов — транзиты и лунные события от времени не зависят.
    if not getattr(chart, "time_unknown", False):
        events += _planner_events(
            chart_id,
            {"planets": chart.planets, "houses": chart.houses,
             "ascendant": chart.ascendant, "midheaven": chart.midheaven},
            from_date, to_date, today, getattr(chart, "timezone", None), tier, tz,
        )

    # planner_longterm — единственный kind, чей `at` может лежать раньше
    # начала окна: медленная планета выбирается по «содержит сегодня»
    # (house_passages.py), а не по попаданию начала в окно, поэтому Плутон,
    # вошедший в дом 14 лет назад, отдаётся с настоящей датой 2012 года и на
    # ЛЮБОМ окне, включающем сегодня (см. CLAUDE.md, «planner_longterm»).
    # `at` и ключ за это не платят — они остаются настоящими; сортировка не
    # должна забрасывать такое событие в начало ленты, за «месяц назад»,
    # поэтому позиция считается по max(at, начало окна ответа), а не по at
    # напрямую.
    #
    # Начало окна приводится к тому же виду, что и `at` — aware-datetime в
    # таймзоне карты, а не голая дата. Раньше здесь сравнивалась голая
    # "2026-08-05" с полным "2026-08-05T13:35:00+03:00": лексически это
    # работало (более короткая строка-префикс всегда меньше продолжающей её
    # длинной), но верно случайно — сравнение опиралось на разную длину строк,
    # а не на однородный формат. Однородный формат делает сравнение понятным
    # само по себе, без знания этого свойства Python-строк.
    # `tz` — всегда pytz-объект (`_tz()` строит его через pytz.timezone/
    # pytz.UTC), поэтому `.localize()` здесь есть и работает: с zoneinfo.
    # ZoneInfo этот вызов упал бы (у него `.localize()` нет, offset задаётся
    # через `tzinfo=` при конструировании). Смещение клэмп берёт на ДАТУ
    # начала окна: для Europe/Moscow до 26.10.2014 это было +04:00, сегодня —
    # +03:00. На текущих окнах (`from_date` всегда «месяц назад» от сегодня)
    # значения не меняет, но если когда-нибудь появится клэмп для
    # исторического окна — offset будет соответствующий дате, не всегда +03:00.
    from_floor_iso = tz.localize(datetime.combine(from_date, datetime.min.time())).isoformat()
    for e in events:
        e["started_before"] = e["at"] < from_floor_iso
    # Вторичный ключ — настоящий `at`, а не хеш `key`: внутри группы,
    # клэмпнутой к началу окна (все started_before делят одно и то же
    # значение max(...)), порядок обязан остаться хронологическим (Плутон
    # 2012 → Нептун 2018 → Сатурн/Уран 2026), а не порядком хеша, который к
    # реальным датам отношения не имеет. `key` — третий ключ, только на
    # случай двух событий с буквально одинаковым `at`.
    events.sort(key=lambda e: (max(e["at"], from_floor_iso), e["at"], e["key"]))

    return {
        "chart_id": chart_id,
        # Отдаётся ЭФФЕКТИВНОЕ окно, уже обрезанное горизонтом, — фронт
        # сравнит его с тем, что просил, и поймёт, что упёрся в край.
        "from_date": from_date.isoformat(),
        "to_date": to_date.isoformat(),
        "timezone": str(tz),
        "horizon": horizon.to_dict(),
        "events": events,
    }
