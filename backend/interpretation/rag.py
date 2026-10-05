"""RAG (Retrieval-Augmented Generation) для чата по натальной карте.

Подход: keyword-search по knowledge_base.json (191 запись).
Без внешних зависимостей — FAISS/sentence-transformers не нужны
при таком объёме базы знаний.

Экспортирует:
    retrieve(question, chart_context) -> list[str]   — релевантные фрагменты
    build_chart_summary(chart)         -> str         — компактный текст карты
    build_planner_block(chart, ...)    -> str         — планер для чата (флаг)
    build_planner_block(chart, ...)    -> str         — планер для чата (флаг)
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path

from backend.ephemeris.ru_names import PLANET_RU as _PLANET_RU, ASPECT_RU as _ASP_RU

logger = logging.getLogger("astro.rag")

# ── загрузка базы знаний ──────────────────────────────────────────────────────

_KB_PATH = Path(__file__).parent / "knowledge_base.json"

def _load_kb() -> list[dict]:
    """Разворачивает иерархический JSON в плоский список {key, text}."""
    try:
        with open(_KB_PATH, encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as e:
        logger.error("Failed to load knowledge_base.json: %s", e)
        return []

    entries: list[dict] = []
    for section, value in raw.items():
        if section == "_meta" or not isinstance(value, dict):
            continue
        for key, text in value.items():
            entries.append({
                "key":     key,
                "section": section,
                "text":    text,
                "tokens":  _tokenize(f"{key} {text}"),
            })
    return entries


def _tokenize(text: str) -> set[str]:
    """Простая токенизация: строчные слова 3+ символов."""
    return set(re.findall(r"[а-яёa-z]{3,}", text.lower()))


_KB: list[dict] | None = None

def _get_kb() -> list[dict]:
    global _KB
    if _KB is None:
        _KB = _load_kb()
    return _KB


# ── keyword retrieval ─────────────────────────────────────────────────────────

# Словарь переводов для матчинга русских терминов с ключами базы
_RU_TO_KEY: dict[str, str] = {
    "солнце": "Sun", "луна": "Moon", "меркурий": "Mercury",
    "венера": "Venus", "марс": "Mars", "юпитер": "Jupiter",
    "сатурн": "Saturn", "уран": "Uranus", "нептун": "Neptune",
    "плутон": "Pluto", "асцендент": "ASC", "асц": "ASC",
    "овен": "Aries", "телец": "Taurus", "близнецы": "Gemini",
    "рак": "Cancer", "лев": "Leo", "дева": "Virgo",
    "весы": "Libra", "скорпион": "Scorpio", "стрелец": "Sagittarius",
    "козерог": "Capricorn", "водолей": "Aquarius", "рыбы": "Pisces",
    "карьера": "career", "деньги": "finance", "финансы": "finance",
    "отношения": "relationships", "любовь": "relationships",
    "здоровье": "health", "работа": "career", "дети": "5",
    "семья": "4", "дом": "house",
    "соединение": "conjunction", "оппозиция": "opposition",
    "трин": "trine", "квадрат": "square", "секстиль": "sextile",
    "ретроградный": "retrograde", "ретро": "retrograde",
}


def retrieve(question: str, chart_context: dict, top_k: int = 6) -> list[str]:
    """Возвращает top_k релевантных фрагментов из базы знаний.

    Args:
        question:      вопрос пользователя
        chart_context: dict с planets, ascendant, houses карты
        top_k:         сколько фрагментов вернуть
    """
    kb = _get_kb()
    if not kb:
        return []

    # Строим набор поисковых токенов из вопроса + маппинга
    q_lower = question.lower()
    q_tokens = _tokenize(q_lower)

    # Добавляем английские эквиваленты русских терминов
    extra: set[str] = set()
    for ru, en in _RU_TO_KEY.items():
        if ru in q_lower:
            extra.update(_tokenize(en))
    q_tokens |= extra

    # Добавляем термины из карты пользователя (планеты, знаки)
    chart_tokens = _chart_tokens(chart_context)
    # Взвешиваем: совпадение с вопросом важнее, чем просто контекст карты

    scored: list[tuple[float, str]] = []
    for entry in kb:
        key_tokens = _tokenize(entry["key"])
        text_tokens = entry["tokens"]

        # Совпадение с вопросом (вес 2) + совпадение с картой (вес 1)
        q_match    = len(q_tokens & (key_tokens | text_tokens))
        chart_match = len(chart_tokens & key_tokens)
        score = q_match * 2 + chart_match

        if score > 0:
            scored.append((score, entry["text"]))

    scored.sort(reverse=True)
    return [text for _, text in scored[:top_k]]


def _chart_tokens(chart: dict) -> set[str]:
    """Извлекает токены из данных карты для контекстуализации поиска."""
    tokens: set[str] = set()
    for p in chart.get("planets") or []:
        tokens.update(_tokenize(str(p.get("name", ""))))
        tokens.update(_tokenize(str(p.get("sign", ""))))
        h = p.get("house")
        if h:
            tokens.add(str(h))
    asc = chart.get("ascendant") or {}
    if asc.get("sign"):
        tokens.update(_tokenize(asc["sign"]))
    return tokens


# ── chart summary для system prompt ──────────────────────────────────────────

_SIGN_RU = {
    "Aries": "Овен", "Taurus": "Телец", "Gemini": "Близнецы",
    "Cancer": "Рак", "Leo": "Лев", "Virgo": "Дева",
    "Libra": "Весы", "Scorpio": "Скорпион", "Sagittarius": "Стрелец",
    "Capricorn": "Козерог", "Aquarius": "Водолей", "Pisces": "Рыбы",
}
# Традиционные управители знаков (по одному управителю на знак)
_SIGN_RULER = {
    "Aries": "Mars", "Taurus": "Venus", "Gemini": "Mercury",
    "Cancer": "Moon", "Leo": "Sun", "Virgo": "Mercury",
    "Libra": "Venus", "Scorpio": "Mars", "Sagittarius": "Jupiter",
    "Capricorn": "Saturn", "Aquarius": "Saturn", "Pisces": "Jupiter",
}


def chat_chart_data(chart: dict, time_unknown: bool) -> dict:
    """Карта в том виде, в каком её видит чат. Общая для ручки чата и прогона
    вопросов (scripts/chat_eval.py) — разойдутся, и прогон проверит не то.

    Без времени рождения — без домов, асцендента, MC и натальной Луны
    (chart_points: её положение известно до ±6°; Луна — с 04.10.2026, шаг 3
    аудита). Аспекты к ним тоже убираются — у них та же неопределённость.
    """
    data = {k: chart.get(k) or ([] if k in ("planets", "aspects", "houses") else {})
            for k in ("planets", "ascendant", "midheaven", "aspects", "houses")}
    if time_unknown:
        from backend.chart_points import planets
        hidden = {"Moon", "Ascendant", "Midheaven", "ASC", "MC"}
        data["planets"] = planets({**data, "time_unknown": True})
        data["ascendant"], data["midheaven"], data["houses"] = {}, {}, []
        data["aspects"] = [a for a in data["aspects"]
                           if a.get("planet1") not in hidden and a.get("planet2") not in hidden]
    return data


def build_chart_summary(chart: dict, time_unknown: bool = False) -> str:
    """Компактный текстовый дамп карты для system prompt (≈400 токенов).

    `time_unknown` — карта без времени рождения. Приложение такую карту
    показывает без домов, асцендента и MC (forecast/facts.py), и чат не должен
    о них говорить: вызывающий не передаёт их сюда (rag_router.chat_chart_data),
    а модели прямо сказано почему. До 02.10.2026 сюда шли «Лев 9.8°, None дом»,
    асцендент и управители домов, посчитанные на полдень.
    """
    lines: list[str] = ["## Натальная карта пользователя\n"]
    if time_unknown:
        lines.append(
            "Время рождения неизвестно: дома, асцендент, MC и точное положение "
            "натальной Луны не определены. О домах, асценденте, MC, управителях "
            "домов и натальной Луне не говори; если спросят — объясни, что для них "
            "нужно время рождения.\n"
        )

    # Планеты
    planets = chart.get("planets") or []
    if planets:
        lines.append("**Планеты:**")
        for p in planets:
            name = _PLANET_RU.get(p.get("name", ""), p.get("name", ""))
            sign = _SIGN_RU.get(p.get("sign", ""), p.get("sign", ""))
            house = f", {p['house']} дом" if p.get("house") else ""
            deg   = round(p.get("degree_in_sign", 0), 1)
            retro = " ℞" if p.get("retrograde") else ""
            lines.append(f"  {name}: {sign} {deg}°{retro}{house}")

    # Асцендент
    asc = chart.get("ascendant") or {}
    if asc.get("sign"):
        sign = _SIGN_RU.get(asc["sign"], asc["sign"])
        lines.append(f"\n**Асцендент:** {sign} {asc.get('degree', '')}°")

    mc = chart.get("midheaven") or {}
    if mc.get("sign"):
        sign = _SIGN_RU.get(mc["sign"], mc["sign"])
        lines.append(f"**MC (Середина Неба):** {sign} {mc.get('degree', '')}°")

    # Управители домов (по знаку на куспиде) — считаем явно, не даём ИИ угадывать
    houses = chart.get("houses") or []
    if houses:
        lines.append("\n**Управители домов** (по знаку на куспиде, традиционные):")
        for h in sorted(houses, key=lambda x: x.get("number", 0)):
            num = h.get("number", "")
            sign_en = h.get("sign", "")
            sign_ru = _SIGN_RU.get(sign_en, sign_en)
            ruler_en = _SIGN_RULER.get(sign_en, "")
            ruler_ru = _PLANET_RU.get(ruler_en, ruler_en)
            if num and ruler_ru:
                lines.append(f"  {num} дом — куспид в {sign_ru} → управитель {ruler_ru}")

    # Ключевые аспекты (топ-8 по орбу)
    aspects = chart.get("aspects") or []
    if aspects:
        sorted_asp = sorted(aspects, key=lambda a: abs(a.get("orb", 9)))
        lines.append("\n**Ключевые аспекты:**")
        for a in sorted_asp[:8]:
            p1  = _PLANET_RU.get(a.get("planet1", ""), a.get("planet1", ""))
            p2  = _PLANET_RU.get(a.get("planet2", ""), a.get("planet2", ""))
            asp_key = a.get("aspect_type") or a.get("aspect", "")
            asp = _ASP_RU.get(asp_key, asp_key)
            orb = a.get("orb", "")
            lines.append(f"  {p1} {asp} {p2} (орб {orb}°)")

    return "\n".join(lines)


def build_transits_block(chart: dict, max_transits: int = 5, today=None, chart_id: str = "",
                         tz: str | None = None) -> str:
    """Блок текущих транзитов для system prompt чата — 3–5 самых значимых
    на сегодня, тем же фактологическим форматом, что и разбор одного
    транзита (см. backend/transit/prompts.py). Считается через Swiss
    Ephemeris, ИИ ничего не вычисляет и не видит дат за пределами списка.

    `tz` — пояс человека (user_tz): дата «Точный аспект» — местная, та же,
    что у события в ленте. Без него — UTC (прогоны и старые тесты)."""
    from datetime import date as _date, datetime
    from backend.day_event import SLOW, counts, points, score
    from backend.transit.engine import calculate_transits, compute_exact_facts
    from backend.transit.prompts import _build_facts_block

    # `today` подаёт только прогон вопросов (scripts/chat_eval.py): «было» и
    # «стало» обязаны считаться на одну дату. Чат его не передаёт.
    today = today or _date.today()
    if not chart.get("planets"):
        return "## Текущие транзиты\nНет данных натальной карты для расчёта транзитов.\n"

    try:
        # Набор точек — day_event.points, тот же, что у ленты: из её чанков
        # берётся пик (_feed_peak), и чанк с другим набором лёг бы под тот же
        # ключ кэша. Медленные планеты — как и раньше.
        planets = points(chart)
        events = calculate_transits(natal_planets=planets, from_date=today, to_date=today,
                                    planet_filter=sorted(SLOW))
    except Exception as e:
        logger.warning("chat transits calc failed: %s", e)
        return "## Текущие транзиты\nНе удалось рассчитать (попробуй чуть позже).\n"

    # Одна шкала (шаг 5 аудита): по баллу day_event.score, при равном — по
    # орбу. До 05.10.2026 — «медленная к личной», топ по орбу.
    significant = [e for e in events if counts(e.natal_planet, e.aspect_type)]
    significant.sort(key=lambda e: (-score(e.transit_planet, e.natal_planet, e.aspect_type), e.peak_orb))
    top = significant[:max_transits]

    if not top:
        return (
            "## Текущие транзиты\n"
            "Сейчас нет значимых активных транзитов (медленная планета к точке "
            "карты). Не выдумывай транзиты — если пользователь спрашивает "
            "«что происходит сейчас», честно скажи, что заметных активаций сейчас нет.\n"
        )

    lines = ["## Текущие транзиты (на сегодня, посчитаны точно)\n"]
    for e in top:
        try:
            # ⚠️ e.peak_date здесь — СЕГОДНЯ, а не пик: движку передано окно в
            # один день, и «пик внутри окна» — это сам день (backend/feed/
            # builder.py, п. 1). До 02.10.2026 эта дата уходила в
            # compute_exact_facts как пик, точный момент искался в ±5 сутках
            # от сегодня, и в промпт шла дата края окна под видом «Точный
            # аспект». Замер на карте владельца 02.10: Уран квадрат Меркурий —
            # чат «точный 27 сентября», лента «10 сентября». Настоящий пик
            # берётся из того же месячного чанка, что показывает лента.
            window = compute_exact_facts(e.transit_planet, e.natal_planet, e.aspect_type, today, chart)
            ev = _feed_peak(chart_id, planets, e, window)
            peak = _date.fromisoformat(ev["peak_date"]) if ev else None
            facts = compute_exact_facts(
                e.transit_planet, e.natal_planet, e.aspect_type, peak or today, chart,
            )
            if ev is None:
                # Пика в чанках нет — честно без даты, чем с выдуманной.
                facts["exact_date"] = None
            elif ev.get("exact_date"):
                # Момент пика ленты → местная дата. До 04.10.2026 шла
                # UTC-дата: пик в 01:30 по Москве чат называл вчерашним.
                from backend.time_utils import utc_naive_to_local
                exact = datetime.fromisoformat(ev["exact_date"])
                facts["exact_date"] = utc_naive_to_local(exact, tz or "UTC").date().isoformat()
            if not chart.get("houses"):
                # Карта без времени рождения: домов нет. Без этого
                # _extract_cusps отдаёт нули, и дом выходит выдуманный.
                facts["transit_house"] = facts["natal_house"] = None
            event_dict = {
                "transit_planet": e.transit_planet,
                "natal_planet": e.natal_planet,
                "aspect_type": e.aspect_type,
                **facts,
            }
            lines.append(_build_facts_block(event_dict))
            lines.append("")
        except Exception as ex:
            logger.warning("chat transit fact build failed for %s: %s", e.transit_planet, ex)

    return "\n".join(lines)


def _feed_peak(chart_id: str, planets: list[dict], e, window: dict):
    """Событие пика текущего прохода (элемент чанка) — из месячных чанков
    ленты (её же кэш).

    Проход — непрерывный отрезок «в орбе», содержащий сегодня (`window`:
    period_start/period_end из compute_exact_facts). Пиков в нём может быть
    несколько (ретроградная петля) — берём ближайшее сближение, как событие
    ленты с наименьшим орбом. Нет ни одного — None: дату не называем.
    """
    from datetime import date as _date
    from backend.feed.builder import _months_between, _transit_chunk

    if not (window.get("period_start") and window.get("period_end")):
        return None
    start, end = window["period_start"], window["period_end"]
    key = (e.transit_planet, e.natal_planet, e.aspect_type)
    best = None
    for y, m in _months_between(_date.fromisoformat(start), _date.fromisoformat(end)):
        for ev in _transit_chunk(chart_id, planets, y, m):
            if (ev["transit_planet"], ev["natal_planet"], ev["aspect_type"]) != key:
                continue
            if start <= ev["peak_date"] <= end and (best is None or ev["peak_orb"] < best["peak_orb"]):
                best = ev
    return best


# Куда отсылать за закрытым периодом. Повторяет сетку замков planner_engine
# (месяц и Луна закрыты только на free → Вега; долгосрочно закрыто на free и
# lite → Лира). Разойдётся с ней — чат будет звать не на тот тариф, поэтому
# при правке is_month_period_locked / is_longterm_locked правится и это.
_OPENS_ON_MONTH = "Веге"
_OPENS_ON_LONGTERM = "Лире"


def _planner_texts(item: dict) -> list[str]:
    """Тексты периода дословно из methodology.json (то, что видит планер)."""
    out = [item[k] for k in ("subtitle",) if item.get(k)]
    out += [f"- {n}" for n in item.get("notes") or []]
    for g in item.get("groups") or []:
        if g.get("heading"):
            # Заголовки в файле уже кончаются двоеточием — второе не ставим.
            out.append(g["heading"].rstrip(":") + ":")
        out += [f"- {i}" for i in g.get("items") or []]
    return out


def _locked_line(head: str, opens_on: str) -> str:
    return f"{head}. Подробный разбор закрыт, открыт на {opens_on}."


def build_planner_block(chart: dict, tier: str | None, user_timezone: str | None, today) -> str:
    """Планер человека для промпта чата (флаг chat_planner_context).

    Источник — тот же build_planner, что отдаёт /planner/monthly, с тем же
    тарифом, поэтому замки срабатывают сами: у закрытого периода payload пуст,
    и в промпт идут только планета, дом и даты (их планер показывает всем).
    ⚠️ Не брать тексты из METHODOLOGY напрямую — так закрытое уйдёт модели, а
    она перескажет его человеку.

    Луна — темой без пунктов: пунктов на неделю ~2,3 тыс. знаков, а проход
    длится ~2 суток. Синхронная (Swiss Ephemeris) — из async только через
    asyncio.to_thread.
    """
    import calendar
    from datetime import date as _date
    from backend.transit.planner_engine import build_planner

    month_start = _date(today.year, today.month, 1)
    month_end = _date(today.year, today.month, calendar.monthrange(today.year, today.month)[1])
    try:
        p = build_planner(
            natal_profile=chart, from_date=month_start, to_date=month_end,
            today=today, user_timezone=user_timezone, tier=tier, with_upcoming=True,
        )
    except Exception as e:  # noqa: BLE001 — без планера чат работает как раньше
        logger.warning("chat planner calc failed: %s", e)
        return ""

    lines = ["## Планер человека — то же, что он видит в приложении в разделе «Планер»", "", "### Сейчас"]
    for s in p["month_sections"]:
        for per in s["periods"]:
            head = f"{s['planet_name']} {per['period']}: {per['house']} дом"
            if per["locked"]:
                lines.append(_locked_line(head, _OPENS_ON_MONTH))
            else:
                lines.append(f"{head}. {per['theme']}")
                lines += _planner_texts(per)
    for w in p["week_days"]:
        if not w["house"]:
            continue
        head = f"Луна {w['date']} — {w['time']}: {w['house']} дом"
        lines.append(_locked_line(head, _OPENS_ON_MONTH) if w["locked"] else f"{head}. {w['theme']}")

    lines += ["", "### Долгосрочно"]
    for l in p["longterm"]:
        head = f"{l['planet_name']} {l['period']}: {l['house']} дом"
        if l["locked"]:
            lines.append(_locked_line(head, _OPENS_ON_LONGTERM))
        else:
            lines.append(f"{head}. {l['theme']}")
            lines += _planner_texts(l)

    if p["upcoming"]:
        lines += ["", "### Ближайшие смены (30 дней)"]
        for u in p["upcoming"]:
            d = _date.fromisoformat(u["date"]).strftime("%d.%m")
            if u["kind"] == "passage":
                lines.append(f"{d} {u['planet_name']} переходит в {u['house']} дом")
            else:
                # Без глагола: род у планет разный («Венера становится
                # ретроградным» — ровно так вышло в первом прогоне).
                turn = "начало ретроградного движения" if u["status"] == "start" else "конец ретроградного движения"
                lines.append(f"{d} {u['planet_name']}: {turn}")
    return "\n".join(lines) + "\n"
