"""Состав PDF по тарифу и тексты разделов.

Бесплатный — как до 29.09.2026: карта и разбор. Вега и Лира (задание
владельца, п. 6):

* Вега — разбор ≈800 слов, 5 самых точных аспектов по короткому абзацу,
  «Главные транзиты: следующие 6 месяцев».
* Лира — разбор ≈2500 слов, 7 аспектов, «Главные транзиты: следующие 12
  месяцев», текущие долгосрочные периоды (готовые тексты планера).

Орион собирается как Лира: на сайте он не продаётся, отдельного состава
владелец не задавал.

Кеш (pdf_section_cache): аспекты — на карту до смены ASPECTS_PROMPT_VERSION;
транзиты — на карту, тариф и месяц. Разбор — строка interpretations с
тарифом не ниже тарифа человека; новый пишется без списания квоты разборов.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from backend.ephemeris.ru_names import ASPECT_RU, PLANET_RU, SIGN_IN_RU
from backend.interpretation.address import ADDRESS_RULE
from backend.time_utils import utcnow

logger = logging.getLogger(__name__)

TIER_RANK = {"free": 0, "lite": 1, "pro": 2, "premium": 3}

# Версия промптов аспектов и транзитов: смена сбрасывает их кеш и отпечаток
# готовых отчётов (новая сборка — с новым текстом).
# 2 — краткие формы в ADDRESS_RULE («ты склонен»), 29.09.2026.
# 3 (только транзиты) — настоящий конец транзита вместо горизонта тарифа
# (29.09.2026): даты лежат в кеше вместе с текстом, без смены версии старые
# остались бы на месяц.
# 3 / 4 — творительный в ADDRESS_RULE, «трин», «работа с энергиями», 30.09.2026.
ASPECTS_PROMPT_VERSION = 3
TRANSITS_PROMPT_VERSION = 4


@dataclass(frozen=True)
class Plan:
    aspects: int = 0          # сколько аспектов с абзацем
    transit_months: int = 0   # горизонт «Главных транзитов»
    transits: int = 0         # сколько транзитов
    longterm: bool = False    # долгосрочные периоды планера


PLANS = {
    "free": Plan(),
    "lite": Plan(aspects=5, transit_months=6, transits=6),
    "pro": Plan(aspects=7, transit_months=12, transits=10, longterm=True),
    "premium": Plan(aspects=7, transit_months=12, transits=10, longterm=True),
}


def plan_for(tier: str | None) -> Plan:
    return PLANS.get(tier or "free", PLANS["free"])


# ── Разбор карты под тариф ─────────────────────────────────

def _word_count(text: str) -> int:
    return len(re.findall(r"\w+", text or ""))


def interpretation_depth(row) -> str:
    """Для какого тарифа написан разбор. У строк до 067 тарифа нет — высший
    тариф, чей объём разбор набирает хотя бы на 70 %: модель пишет меньше
    заказанного, а ровно по лимиту не пишет никогда."""
    if getattr(row, "tier", None):
        return row.tier
    from backend.auth.rate_limits import TIER_FLAGS
    words = _word_count(row.content)
    best = "free"
    for t in ("free", "lite", "pro", "premium"):
        if words >= 0.7 * TIER_FLAGS[t]["interpretation_word_limit"]:
            best = t
    return best


def pick_interpretation(db, chart_id: str, tier: str):
    """Самый свежий разбор не короче тарифа человека и без родовых форм, или
    None — тогда пишется новый.

    Родовые формы (решение владельца 29.09.2026): сохранённые разборы массово
    не переписываются, и до правила от 28.09 модель писала «ты склонен».
    На сайте такой разбор остаётся как есть, а в PDF — документ, который
    хранят и пересылают, — берётся только чистый. Грязный не удаляется: PDF
    пишет рядом новый (без квоты разборов), и тот становится самым свежим."""
    from backend.interpretation.gender_check import gendered_you
    from backend.models import Interpretation
    rows = (
        db.query(Interpretation)
        .filter(Interpretation.chart_id == chart_id)
        .order_by(Interpretation.created_at.desc())
        .all()
    )
    need = TIER_RANK.get(tier, 0)
    return next((r for r in rows
                 if TIER_RANK.get(interpretation_depth(r), 0) >= need and not gendered_you(r.content)), None)


def natal_profile(chart) -> dict:
    return {
        "planets": chart.planets, "houses": chart.houses, "aspects": chart.aspects,
        "ascendant": chart.ascendant, "midheaven": chart.midheaven,
        "time_unknown": chart.time_unknown,
    }


class SectionError(RuntimeError):
    """Раздел не собрался — сборка отчёта падает целиком (status failed)."""


async def stream_text(request) -> tuple[str, str, float]:
    """Текст модели стримом → (текст, движок, цена $).

    Стрим, а не generate(): у нестримингового пути жёсткий потолок 30 с
    (router._try_engine), а разбор Лиры в 2500 слов идёт 1,5–2 минуты — на
    generate() он ни разу не успел бы и уходил бы в шаблон. Стрим сам
    отбраковывает обрезанный ответ (IncompleteInterpretation) и зовёт детектор
    родовых форм.

    Цена — по токенам последнего стрима движка. Поле живёт на синглтоне
    движка и общее для одновременных запросов; здесь это безопасно, потому
    что зовётся только из Celery-воркера (процесс — одна задача за раз). Из
    ручки api так считать нельзя. Ответ из кеша стрима — 0.
    """
    from backend.interpretation.router import _cost_per_1k, get_router
    router = get_router()
    for e in router._engines:
        e._last_stream_tokens = 0
    text = "".join([chunk async for chunk in router.stream(request)])
    engine = request.engine_used or "none"
    if not text.strip() or engine in ("template", "none"):
        raise SectionError(f"{request.context}: движок {engine}")
    tokens = next((getattr(e, "_last_stream_tokens", 0) for e in router._engines if e.name == engine), 0)
    return text, engine, (tokens or 0) / 1000 * _cost_per_1k(engine)


async def new_interpretation(db, chart, tier: str):
    """Написать разбор тарифа и сохранить с тарифом. Квота разборов НЕ
    списывается (решение владельца: PDF сам решает, что разбор короче
    тарифа, человек его не заказывал). Возвращает (строка, цена $)."""
    from backend.cache import make_profile_hash
    from backend.interpretation.base import InterpretationRequest
    from backend.models import Interpretation

    profile = natal_profile(chart)
    text, engine, cost = await stream_text(InterpretationRequest(natal_profile=profile, tier=tier))
    row = Interpretation(
        chart_id=chart.id, profile_hash=make_profile_hash(profile),
        engine=engine, content=text, sections=None, tier=tier,
    )
    db.add(row)
    db.commit()
    return row, cost


# ── Даты словами ───────────────────────────────────────────

_MONTHS_GEN = ("января", "февраля", "марта", "апреля", "мая", "июня", "июля",
               "августа", "сентября", "октября", "ноября", "декабря")


def day_words(d: date, year: bool = True) -> str:
    return f"{d.day} {_MONTHS_GEN[d.month - 1]}" + (f" {d.year}" if year else "")


def range_words(start: date, end: date, today: date) -> str:
    """«с 3 марта по 18 июня 2027»; уже идёт — «до 18 июня 2027»."""
    if start <= today:
        return f"до {day_words(end)}"
    return f"с {day_words(start, year=start.year != end.year)} по {day_words(end)}"


# ── Кеш разделов ───────────────────────────────────────────

def cache_get(db, chart_id: str, key: str):
    from backend.models import PdfSectionCache
    row = db.query(PdfSectionCache).filter_by(chart_id=chart_id, key=key).first()
    return row.content if row else None


def cache_put(db, chart_id: str, key: str, content) -> None:
    from backend.models import PdfSectionCache
    row = db.query(PdfSectionCache).filter_by(chart_id=chart_id, key=key).first()
    if row:
        row.content, row.created_at = content, utcnow()
    else:
        db.add(PdfSectionCache(chart_id=chart_id, key=key, content=content, created_at=utcnow()))
    db.commit()


def aspects_key(tier: str) -> str | None:
    n = plan_for(tier).aspects
    return f"aspects:v{ASPECTS_PROMPT_VERSION}:{n}" if n else None


def transits_key(tier: str, today: date) -> str | None:
    if not plan_for(tier).transits:
        return None
    return f"transits:v{TRANSITS_PROMPT_VERSION}:{today:%Y-%m}:{tier}"


# ── Модель: абзацы по списку ──────────────────────────────

_STYLE = (
    "Пиши просто и по-человечески, как умный друг, который разбирается в "
    "астрологии: без эзотерики, без мистических обещаний, без слов «энергия "
    "Вселенной», «карма», «чакры», «работа с энергиями». Аспект в 120° — «трин», "
    "не «тригон». Не называй себя и не упоминай, кто пишет "
    "текст. " + ADDRESS_RULE
)


def _parse_numbered(text: str, n: int) -> list[str]:
    """«### 1 … ### n» → n абзацев. Другое число — ошибка: модель сбилась, и
    склеивать тексты с чужими заголовками хуже, чем не собрать PDF."""
    parts = re.split(r"^\s*#{2,3}\s*(\d+)\s*$", text or "", flags=re.M)
    found = {int(parts[i]): parts[i + 1].strip() for i in range(1, len(parts) - 1, 2)}
    out = [found.get(i + 1, "") for i in range(n)]
    if not all(out):
        raise SectionError(f"ждали {n} абзацев, пришло {len([o for o in out if o])}")
    return [re.sub(r"\s*\n\s*", " ", o) for o in out]


async def _numbered_texts(chart, tier: str, prompt: str, n: int, contour: str) -> tuple[list[str], float]:
    from backend.interpretation.base import InterpretationRequest
    text, _, cost = await stream_text(InterpretationRequest(
        natal_profile=natal_profile(chart), context=contour, tier=tier,
        # 1000 — нижняя граница явного лимита (resolve_word_limit); от неё
        # считаются max_tokens и срок стрима, самих абзацев просим меньше.
        word_limit=1000, custom_prompt=prompt,
    ))
    return _parse_numbered(text, n), cost


def _where(p: dict) -> str:
    s = f"{PLANET_RU.get(p.get('name'), p.get('name'))} {SIGN_IN_RU.get(p.get('sign'), '')}".strip()
    return f"{s}, {p['house']} дом" if p.get("house") else s


# ── Аспекты ────────────────────────────────────────────────

MAJOR = ("conjunction", "opposition", "square", "trine", "sextile")
_SKIP = ("North Node", "South Node")


def top_aspects(aspects, n: int, time_unknown: bool = False) -> list[dict]:
    """n самых точных мажорных аспектов между планетами (без узлов; без
    времени рождения — и без Луны, ASC, MC: chart_points, шаг 3 аудита)."""
    from backend.chart_points import UNKNOWN_TIME_HIDDEN
    skip = set(_SKIP) | (UNKNOWN_TIME_HIDDEN if time_unknown else set())
    items = [
        a for a in (aspects or [])
        if a.get("aspect_type") in MAJOR and a.get("planet1") not in skip and a.get("planet2") not in skip
    ]
    return sorted(items, key=lambda a: float(a.get("orb") or 0))[:n]


def aspect_title(a: dict) -> str:
    return f"{PLANET_RU.get(a['planet1'], a['planet1'])} и {PLANET_RU.get(a['planet2'], a['planet2'])} — {ASPECT_RU[a['aspect_type']]}"


def aspects_prompt(chart, items: list[dict]) -> str:
    by = {p.get("name"): p for p in chart.planets or []}
    lines = []
    for i, a in enumerate(items, 1):
        p1, p2 = by.get(a["planet1"], {"name": a["planet1"]}), by.get(a["planet2"], {"name": a["planet2"]})
        lines.append(f"{i}. {aspect_title(a)} (орб {float(a.get('orb') or 0):.1f}°): {_where(p1)}; {_where(p2)}")
    return (
        "Ниже — самые точные аспекты натальной карты человека. Для каждого "
        "напиши один абзац из 3–4 предложений (50–70 слов): как это сочетание "
        "проявляется в характере и в жизни, в чём его сила и где нужна "
        "осторожность. Без общих слов о самом аспекте — только про этого "
        f"человека. {_STYLE}\n\n"
        "Формат ответа строго такой, без вступления и заключения:\n"
        "### 1\nабзац\n### 2\nабзац\n… и так до последнего номера.\n\n"
        + "\n".join(lines)
    )


async def aspect_section(db, chart, tier: str) -> tuple[list[dict], float]:
    n = plan_for(tier).aspects
    if not n:
        return [], 0.0
    key = aspects_key(tier) + _nt(chart)
    cached = cache_get(db, chart.id, key)
    if cached:
        return cached, 0.0
    items = top_aspects(chart.aspects, n, bool(chart.time_unknown))
    if not items:
        return [], 0.0
    texts, cost = await _numbered_texts(chart, tier, aspects_prompt(chart, items), len(items), "pdf_aspects")
    out = [
        {"title": aspect_title(a), "kind": a["aspect_type"], "orb": float(a.get("orb") or 0), "text": t}
        for a, t in zip(items, texts)
    ]
    cache_put(db, chart.id, key, out)
    return out, cost


# ── Главные транзиты ───────────────────────────────────────

_SLOW = ("Jupiter", "Saturn", "Uranus", "Neptune", "Pluto")
_TARGETS = ("Sun", "Moon", "Mercury", "Venus", "Mars")
_W_PLANET = {"Pluto": 5, "Neptune": 4, "Uranus": 4, "Saturn": 4, "Jupiter": 3}
_W_NATAL = {"Sun": 3, "Moon": 3, "Venus": 2, "Mars": 2, "Mercury": 2}
_W_ASPECT = {"conjunction": 3, "opposition": 2.5, "square": 2.5, "trine": 1.5, "sextile": 1}
_DATIVE = {
    "Sun": "Солнцу", "Moon": "Луне", "Mercury": "Меркурию", "Venus": "Венере", "Mars": "Марсу",
}
# «соединение С Марсом», остальные — «квадрат К Марсу».
_INSTR = {
    "Sun": "Солнцем", "Moon": "Луной", "Mercury": "Меркурием", "Venus": "Венерой", "Mars": "Марсом",
}


def transit_title(tp: str, natal: str, asp: str) -> str:
    to = f"с {_INSTR[natal]}" if asp == "conjunction" else f"к {_DATIVE[natal]}"
    return f"{PLANET_RU[tp]} — {ASPECT_RU[asp]} {to}"


# Насколько вперёд искать конец транзита, идущего за горизонтом тарифа.
# Один проход Плутона с ретроградной петлёй укладывается в 2–2,5 года.
_TAIL_DAYS = 3 * 365


def _real_ends(natal, keys, horizon: date) -> dict[tuple, date | None]:
    """Настоящий конец транзитов, не кончившихся к горизонту.

    ⚠️ Без этого конец обрезался горизонтом тарифа и выглядел настоящим: один
    и тот же «Юпитер — квадрат к Венере» у Веги шёл «до 3 апреля», у Лиры —
    «до 3 июня» (задание владельца 29.09.2026). None — не кончился и за
    _TAIL_DAYS, тогда пишется «продолжается и после».
    """
    from backend.transit.engine import calculate_transits
    tail = horizon + timedelta(days=_TAIL_DAYS)
    events = calculate_transits(
        [p for p in natal if p["name"] in {k[1] for k in keys}], horizon, tail,
        planet_filter=list({k[0] for k in keys}),
    )
    out: dict[tuple, date | None] = {k: None for k in keys}
    for e in events:
        k = (e.transit_planet, e.natal_planet, e.aspect_type)
        # Проход, идущий через горизонт, открыт с первого дня поиска.
        if k in out and e.start_date <= horizon.isoformat() and e.end_date < tail.isoformat():
            out[k] = date.fromisoformat(e.end_date[:10])
    return out


def main_transits(planets, today: date, months: int, n: int) -> list[dict]:
    """Медленные планеты к личным натальным за `months` месяцев вперёд.
    Проходы одного транзита (ретроградные возвраты) склеиваются в один
    отрезок; берутся n самых весомых, показываются по дате начала. Конец —
    настоящий, а не горизонт тарифа (_real_ends)."""
    from backend.transit.engine import calculate_transits

    end = today + timedelta(days=round(months * 30.44))
    natal = [p for p in planets or [] if p.get("name") in _TARGETS and p.get("longitude") is not None]
    events = calculate_transits(natal, today, end, planet_filter=list(_SLOW))
    merged: dict[tuple, dict] = {}
    for e in events:
        if e.aspect_type not in _W_ASPECT:
            continue
        k = (e.transit_planet, e.natal_planet, e.aspect_type)
        m = merged.setdefault(k, {"start": e.start_date, "end": e.end_date, "orb": e.peak_orb, "exact": []})
        m["start"], m["end"] = min(m["start"], e.start_date), max(m["end"], e.end_date)
        m["orb"] = min(m["orb"], e.peak_orb)
        if e.exact_date:
            m["exact"].append(e.exact_date[:10])
    ranked = sorted(
        merged.items(),
        key=lambda kv: -(_W_PLANET[kv[0][0]] * _W_NATAL[kv[0][1]] * _W_ASPECT[kv[0][2]] + (1 if kv[1]["orb"] < 0.5 else 0)),
    )[:n]
    # Движок досчитывает окно на 3 дня за to_date: конец не раньше горизонта
    # значит, что транзит к нему не кончился.
    cut = [k for k, m in ranked if m["end"][:10] >= end.isoformat()]
    tails = _real_ends(natal, cut, end) if cut else {}
    out = []
    for (tp, np_, asp), m in sorted(ranked, key=lambda kv: kv[1]["start"]):
        s, e = date.fromisoformat(m["start"][:10]), date.fromisoformat(m["end"][:10])
        if (tp, np_, asp) in tails:
            e = tails[(tp, np_, asp)]
        if e is None:
            when = (f"с {day_words(s)}, " if s > today else "") + f"продолжается и после {day_words(end)}"
        else:
            when = range_words(s, e, today)
        exact = sorted({x for x in m["exact"] if today.isoformat() <= x <= end.isoformat()})
        out.append({
            "planet": tp, "natal": np_, "kind": asp,
            "title": transit_title(tp, np_, asp),
            "when": when,
            "exact": ", ".join(day_words(date.fromisoformat(x)) for x in exact[:3]),
        })
    return out


def transits_prompt(chart, items: list[dict], months: int) -> str:
    by = {p.get("name"): p for p in chart.planets or []}
    lines = [
        f"{i}. {t['title']} ({t['when']}); натальное: {_where(by.get(t['natal'], {'name': t['natal']}))}"
        for i, t in enumerate(items, 1)
    ]
    return (
        f"Ниже — главные транзиты человека на ближайшие {months} месяцев. Для "
        "каждого напиши один абзац из 2–3 предложений (35–55 слов): какая тема "
        "приходит в это время и как её прожить с пользой. Дат не повторяй — "
        f"они стоят рядом. {_STYLE}\n\n"
        "Формат ответа строго такой, без вступления и заключения:\n"
        "### 1\nабзац\n### 2\nабзац\n… и так до последнего номера.\n\n"
        + "\n".join(lines)
    )


async def transit_section(db, chart, tier: str, today: date) -> tuple[list[dict], float]:
    plan = plan_for(tier)
    if not plan.transits:
        return [], 0.0
    key = transits_key(tier, today) + _nt(chart)
    cached = cache_get(db, chart.id, key)
    if cached:
        return cached, 0.0
    import asyncio
    from backend.chart_points import planets as natal_planets
    items = await asyncio.to_thread(main_transits, natal_planets(chart), today, plan.transit_months, plan.transits)
    if items:
        texts, cost = await _numbered_texts(
            chart, tier, transits_prompt(chart, items, plan.transit_months), len(items), "pdf_transits")
        for t, text in zip(items, texts):
            t["text"] = text
    else:
        cost = 0.0
    cache_put(db, chart.id, key, items)
    return items, cost


# ── Долгосрочные периоды — готовые тексты планера ──────────

def longterm_section(chart, today: date, tz: str | None = None) -> list[dict]:
    """`tz` — пояс человека (user_tz): границы периодов — местные даты.
    Без времени рождения раздела нет: домов нет (chart_points, шаг 3 аудита;
    до 04.10.2026 периоды шли по полуденным домам)."""
    if chart.time_unknown:
        return []
    from backend.time_utils import utc_naive_to_local
    from backend.transit.house_passages import compute_planner_periods
    from backend.transit.planner_engine import _KEY_TO_ENG, _planet_lead, _unlocked_payload

    periods = compute_planner_periods(
        natal_profile=natal_profile(chart), from_date=today, to_date=today + timedelta(days=30), today=today,
        user_timezone=tz, with_moon_week=False,
    )
    out = []
    for p in periods.get("slow_planets", []):
        house = p.get("house")
        eng = _KEY_TO_ENG.get(p["planet_key"])
        if not house or not eng:
            continue
        s = utc_naive_to_local(datetime.fromisoformat(p["start_dt"]), tz or "UTC").date()
        e = utc_naive_to_local(datetime.fromisoformat(p["end_dt"]), tz or "UTC").date()
        out.append({
            "title": f"{p['planet_name']} в {house} доме",
            "lead": _planet_lead(eng),
            "when": range_words(s, e, today),
            **_unlocked_payload(eng, house),
        })
    return out


# ── Отпечаток ──────────────────────────────────────────────

def _nt(chart) -> str:
    """Метка ключей у карты без времени рождения (шаг 3, 04.10.2026): их
    прежние тексты брали натальную Луну, ASC и дома. Только у них — общая
    версия перегенерировала бы платные тексты всех карт."""
    return ":nt" if getattr(chart, "time_unknown", False) else ""


def fingerprint(interp_id: str | None, tier: str, today: date, chart=None) -> str | None:
    """Из чего собран отчёт. None — разбора под тариф нет, отчёт новый."""
    if not interp_id:
        return None
    nt = _nt(chart) if chart is not None else ""
    parts = [f"i:{interp_id}"] + [k + nt for k in (aspects_key(tier), transits_key(tier, today)) if k]
    if plan_for(tier).longterm:
        # l2 (04.10.2026, шаг 2б): границы периодов — настоящие, а не край окна.
        parts.append(f"l2:{today:%Y-%m}")
    return "|".join(p for p in parts if p)


@dataclass
class Report:
    """Всё, что нужно рендеру сверх карты."""
    tier: str
    interpretation: str = ""
    aspects: list = field(default_factory=list)
    transits: list = field(default_factory=list)
    transit_months: int = 0
    longterm: list = field(default_factory=list)
