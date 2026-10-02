"""Прогон типичных вопросов через чат Аристеи — для сравнения «было | стало».

Запускается из .github/workflows/chat-eval.yml (ручной запуск), локально не
гоняется: боевого ключа DeepSeek на машине разработчика нет.

    python scripts/chat_eval.py run --date 2026-10-02 [--flag] [--tier premium] --out a.json
    python scripts/chat_eval.py report a.json [b.json] --out report.md

Промпт собирается ТЕМИ ЖЕ функциями, что и ручка чата (rag_router.rag_chat):
build_chart_summary, retrieve, build_transits_block, build_planner_block,
_system_prompt, _classify_topic. Своего промпта здесь нет и быть не должно —
иначе прогон проверял бы копию, а не чат.

Чего прогон намеренно НЕ повторяет:
* истории и памяти — каждый вопрос задаётся с чистого листа, иначе ответы
  зависели бы от порядка вопросов и от прошлых прогонов;
* потока — ответ берётся целиком, параметры модели те же (`CHAT_MAX_TOKENS`,
  temperature 0.7, thinking выключен).

⚠️ Дата фиксируется (`--date`), а не берётся «сегодня»: при сравнении
«было | стало» обе стороны обязаны считать транзиты на один день — иначе
разница в ответах будет от неба, а не от правки.

⚠️ Репозиторий публичный: в отчёте ответы по карте живого человека. Отчёт
уходит только в Telegram владельцу; в лог пишутся одни счётчики. Не печатать
ответы и промпт в stdout и не выкладывать отчёт артефактом.

Данные рождения — секрет CHAT_EVAL_BIRTH (JSON: date, time, place), а не файл
в репозитории, по той же причине.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Первым в пути — СВОЙ корень: при сравнении с прошлым коммитом его копия
# лежит рядом, и импорт обязан взять backend из той же копии, что и скрипт.
sys.path.insert(0, str(ROOT))

QUESTIONS = Path(__file__).with_name("chat_eval_questions.json")


# ── карта ─────────────────────────────────────────────────────────────────────

async def _chart(birth: dict) -> tuple[dict, str | None, bool]:
    """Карта в том виде, в каком её хранит NatalChart (main._build_chart)."""
    from backend.ephemeris.calculator import calculate_full_chart
    from backend.ephemeris.geo import geocode_place, resolve_utc_datetime
    from backend.schemas import AspectData, HouseData, PlanetPosition, PointData

    geo = await geocode_place(birth["place"])
    utc_dt, time_unknown, _ = resolve_utc_datetime(
        birth_date=birth["date"], birth_time=birth.get("time"), timezone=geo.timezone,
    )
    c, aspects = calculate_full_chart(
        utc_dt=utc_dt, latitude=geo.latitude, longitude=geo.longitude,
        house_system=birth.get("house_system", "placidus"), time_unknown=time_unknown,
    )
    planets = [PlanetPosition(
        name=p.name, longitude=p.longitude, sign=p.sign, degree_in_sign=p.degree_in_sign,
        house=p.house if not time_unknown else None, retrograde=p.retrograde,
    ).model_dump() for p in c.planets]
    point = lambda x: PointData(sign=x.sign, degree=x.degree, longitude=x.longitude).model_dump() if x else {}
    chart = {
        "planets": planets,
        "ascendant": point(c.ascendant),
        "midheaven": point(c.midheaven),
        "aspects": [AspectData(
            planet1=a.planet1, planet2=a.planet2, aspect_type=a.aspect_type, angle=a.angle,
            orb=a.orb, applying=a.applying, importance=getattr(a, "importance", "low"),
        ).model_dump() for a in aspects],
        "houses": [HouseData(number=h.number, sign=h.sign, degree=h.degree).model_dump() for h in c.houses],
    }
    return chart, geo.timezone, time_unknown


# ── модель ────────────────────────────────────────────────────────────────────

async def _answer(system: str, question: str) -> dict:
    """Ответ ТЕМ ЖЕ генератором, что отвечает человеку (rag_router._sse_generator):
    поток, проверка рода по фразам и переписывание. До 02.10.2026 прогон звал
    модель своим запросом в обход — и мерил ответ, которого человек не видит.

    user_id пустой — генератор ничего не пишет в историю (_persist_turn).
    """
    from backend.interpretation import rag_router

    turn: dict = {}
    parts, error = [], None
    messages = [{"role": "system", "content": system}, {"role": "user", "content": question}]
    async for frame in rag_router._sse_generator(messages, "premium", turn=turn):
        body = frame[6:].strip() if frame.startswith("data: ") else ""
        if not body or body == "[DONE]":
            continue
        data = json.loads(body)
        if data.get("error"):
            error = data["error"]
        elif "text" in data:
            parts.append(data["text"])
    return {
        "text": "".join(parts),
        "finish_reason": error or turn.get("finish_reason"),
        "prompt_tokens": turn.get("tokens", 0),
        "completion_tokens": 0,
        "gender_rewrites": turn.get("gender_rewrites", 0),
        "gender_unfixed": turn.get("gender_unfixed", 0),
    }


async def run(args) -> None:
    from backend.interpretation import rag_router
    from backend.interpretation.rag import build_chart_summary, build_transits_block, chat_chart_data, retrieve

    birth = json.loads(os.environ["CHAT_EVAL_BIRTH"])
    day = date.fromisoformat(args.date) if args.date else datetime.now(timezone(timedelta(hours=3))).date()
    stored, tz, time_unknown = await _chart(birth)
    chart = chat_chart_data(stored, time_unknown)  # как в rag_chat

    # Сборка — как в rag_chat. Транзиты и планер — один раз на прогон: в чате
    # они тоже кэшируются на сутки, а не считаются на каждый вопрос.
    summary = build_chart_summary(chart, time_unknown)
    transits = await asyncio.to_thread(build_transits_block, chart, 5, day, "chat-eval")
    planner = ""
    if args.flag and not time_unknown:
        from backend.interpretation.rag import build_planner_block
        profile = {k: chart[k] for k in ("planets", "houses", "ascendant", "midheaven")}
        planner = await asyncio.to_thread(build_planner_block, profile, args.tier, tz, day)
    p1 = ""
    if args.flag:
        # Контекст P1 — те же функции, что в rag_router._get_p1_block. Окно
        # уведомлений — значения по умолчанию (08:00–22:00), тариф — --tier,
        # без лимита сообщений; кэша прогноза дня у прогона нет.
        from types import SimpleNamespace
        from backend.interpretation import chat_context as cc
        obj = SimpleNamespace(id="chat-eval", timezone=tz, time_unknown=time_unknown, **stored)
        p1 = await asyncio.to_thread(lambda: "\n".join([
            cc.day_block(obj, day, tz, "08:00", "22:00"),
            cc.upcoming_block(obj, day, tz, "08:00", "22:00", args.tier),
            cc.tier_block(args.tier, None, None, None),
        ]) + "\n")

    items = []
    for item in json.loads(QUESTIONS.read_text(encoding="utf-8")):
        q = item["q"]
        topic = await rag_router._classify_topic(q)
        system = rag_router._system_prompt(
            summary, retrieve(q, chart, top_k=6), "", transits, planner, today=day, p1_block=p1,
        )
        answers = []
        for _ in range(args.repeats):
            if topic != "astrology":
                # Как в чате: чужая тема до модели не доходит, ответ фиксированный.
                from backend.interpretation.chat_context import PRODUCT_TOPICS, product_reply
                text = (product_reply(topic, args.tier) if topic in PRODUCT_TOPICS
                        else rag_router.OFF_TOPIC_REPLIES.get(topic, rag_router.OFF_TOPIC_REPLY))
                answers.append({"text": text,
                                "finish_reason": "off_topic", "prompt_tokens": 0, "completion_tokens": 0})
            else:
                answers.append(await _answer(system, q))
        for a in answers:
            a["checks"] = check(a["text"], system, day)
        items.append({**item, "topic": topic, "system": system, "answers": answers})

    commit = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
                            capture_output=True, text=True).stdout.strip()
    out = {
        "meta": {"commit": commit, "date": day.isoformat(), "flag": bool(args.flag),
                 "tier": args.tier, "repeats": args.repeats, "time_unknown": time_unknown},
        "items": items,
    }
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    # В лог — только счётчики (см. докстринг модуля).
    bad = sum(1 for i in items for a in i["answers"] for k in VIOLATIONS if a["checks"][k])
    print(f"commit={commit} date={day} flag={args.flag} вопросов={len(items)} ответов с нарушениями={bad}")


# ── проверки ──────────────────────────────────────────────────────────────────
# Проверка кодом, без второй модели-судьи: правило либо выполнено, либо нет.
# Совпадения по словам приблизительны — это подсказка, куда смотреть глазами,
# а не приговор; поэтому в отчёт идёт и сам найденный фрагмент.

_MONTHS = ("января", "февраля", "марта", "апреля", "мая", "июня", "июля",
           "августа", "сентября", "октября", "ноября", "декабря")
_DATE_WORDS = re.compile(
    r"(?<!\d)(\d{1,2})(?:\s*(?:[-–—]|по|и|до)\s*(\d{1,2}))?\s+(" + "|".join(_MONTHS) + r")", re.I)
# «9.8°» — градус, не дата; поэтому запрет на ° и цифру после.
_DATE_DOTS = re.compile(r"(?<![\d.])(\d{1,2})\.(\d{1,2})(?:\.\d{2,4})?(?![\d°])")


def _dates(text: str) -> set[tuple[int, int]]:
    found = set()
    for m in _DATE_WORDS.finditer(text):
        month = _MONTHS.index(m.group(3).lower()) + 1
        found.add((int(m.group(1)), month))
        if m.group(2):
            found.add((int(m.group(2)), month))
    for m in _DATE_DOTS.finditer(text):
        d, mo = int(m.group(1)), int(m.group(2))
        if 1 <= d <= 31 and 1 <= mo <= 12:
            found.add((d, mo))
    return found


_L = r"(?<![а-яё])"
_PLANETS = {
    "Солнце": _L + r"солнц", "Луна": _L + r"лун[аеуыо]", "Меркурий": _L + r"меркури",
    "Венера": _L + r"венер", "Марс": _L + r"марс", "Юпитер": _L + r"юпитер",
    "Сатурн": _L + r"сатурн", "Уран": _L + r"уран(?:а|у|ом|е)?(?![а-яё])",
    "Нептун": _L + r"нептун", "Плутон": _L + r"плутон", "Узел": _L + r"(?:узл|узел)",
}
_ASPECTS = {
    "соединение": _L + r"соединени", "оппозиция": _L + r"оппозици", "квадрат": _L + r"квадрат",
    "трин": _L + r"трин(?:а|ом|е|у)?(?![а-яё])", "секстиль": _L + r"секстил",
}


def _find(table: dict, text: str) -> set[str]:
    low = text.lower()
    return {k for k, rx in table.items() if re.search(rx, low)}


def _units(system: str) -> list[str]:
    """Единицы фактов промпта: каждая строка и каждый блок между пустыми
    строками (блок транзита — три строки: транзитная, натальная, аспект)."""
    return system.splitlines() + re.split(r"\n\s*\n", system)


def check(text: str, system: str, day: date) -> dict:
    allowed = _dates(system) | {(day.day, day.month)}
    bad_dates = sorted(f"{d:02d}.{m:02d}" for d, m in _dates(text) - allowed)

    units = [(_find(_PLANETS, u), _find(_ASPECTS, u)) for u in _units(system)]
    bad_aspects = []
    for sent in re.split(r"(?<=[.!?…])\s+|\n+", text):
        planets, aspects = _find(_PLANETS, sent), _find(_ASPECTS, sent)
        if len(planets) < 2 or not aspects:
            continue
        if not any(len(planets & up) >= 2 and aspects & ua for up, ua in units):
            bad_aspects.append(sent.strip()[:160])

    from backend.payments.common import prices_on
    allowed_prices = set(prices_on().values())
    prices = [int(re.sub(r"\D", "", m)) for m in re.findall(r"(\d[\d  ]{0,6})\s*(?:₽|руб)", text)]

    from backend.interpretation.gender_check import gendered_you
    return {
        "dates_not_in_data": bad_dates,
        "aspects_not_in_data": bad_aspects,
        "wrong_prices": [p for p in prices if p not in allowed_prices],
        "ai_words": re.findall(r"(?<![A-Za-zА-Яа-яЁё])(?:AI|ИИ)(?![A-Za-zА-Яа-яЁё])|нейросет\w*", text),
        "formal_you": re.findall(r"(?<![а-яё])(?:вы|вас|вам|вами|ваш\w*)(?![а-яё])", text.lower()),
        "gendered": gendered_you(text),
        # Справочно, не нарушения:
        "says_not_see": bool(re.search(r"не вижу", text, re.I)),
        "names_tariff": sorted(set(re.findall(r"(?<![а-яё])(Вег[аеиу]|Лир[аеуы]|Орион\w*)", text))),
        "words": len(text.split()),
    }


VIOLATIONS = ("dates_not_in_data", "aspects_not_in_data", "wrong_prices", "ai_words", "formal_you", "gendered")
_LABELS = {
    "dates_not_in_data": "даты не из данных",
    "aspects_not_in_data": "аспекты не из данных",
    "wrong_prices": "цены не из тарифов",
    "ai_words": "«AI/ИИ»",
    "formal_you": "на «вы»",
    "gendered": "род",
}


# ── отчёт ─────────────────────────────────────────────────────────────────────

def _issues(a: dict) -> list[str]:
    c = a["checks"]
    out = [f"{_LABELS[k]}: {', '.join(map(str, c[k]))}" for k in VIOLATIONS if c[k]]
    if a.get("gender_rewrites"):
        out.append(f"переписано фраз с родом: {a['gender_rewrites']}")
    if a.get("gender_unfixed"):
        out.append(f"не удалось переписать: {a['gender_unfixed']}")
    if c["says_not_see"]:
        out.append("справочно: «не вижу»")
    if c["names_tariff"]:
        out.append(f"справочно: тариф — {', '.join(c['names_tariff'])}")
    return out


def _count(item: dict) -> int:
    return sum(1 for a in item["answers"] for k in VIOLATIONS if a["checks"][k])


def _meta(m: dict) -> str:
    return (f"коммит {m['commit']}, дата {m['date']}, флаг chat_planner_context "
            f"{'вкл' if m['flag'] else 'выкл'}, тариф {m['tier']}, повторов {m['repeats']}")


def report(args) -> None:
    runs = [json.loads(Path(p).read_text(encoding="utf-8")) for p in args.files]
    # Проверки пересчитываются ЗДЕСЬ, текущим кодом, для обеих сторон: «было»
    # прогонялось старой копией, и её детектор мог не знать новых оборотов —
    # сравнение показало бы «стало хуже» там, где просто стали лучше ловить.
    for r in runs:
        day = date.fromisoformat(r["meta"]["date"])
        for it in r["items"]:
            for a in it["answers"]:
                a["checks"] = check(a["text"], it["system"], day)
    # Порядок в отчёте: «было» (второй файл), потом «стало» (первый).
    cur, base = runs[0], (runs[1] if len(runs) > 1 else None)
    cols = [("Было", base), ("Стало", cur)] if base else [("Ответ", cur)]

    # В лог — разбивка по вопросам и видам: числа и метка темы, без текста
    # ответов (решение владельца 02.10.2026; репозиторий публичный). По ней
    # прогон разбирается, не видя отчёта. Проверки здесь уже пересчитаны
    # текущим кодом для обеих сторон.
    for name, r in cols:
        print(f"{name}: {_meta(r['meta'])}")
        for it in r["items"]:
            counts = {k: sum(1 for a in it["answers"] if a["checks"][k]) for k in VIOLATIONS}
            found = " ".join(f"{_LABELS[k]}={n}" for k, n in counts.items() if n) or "чисто"
            rewrites = sum(a.get("gender_rewrites", 0) for a in it["answers"])
            print(f"  q{it['id']:02d} тема={it['topic']} {found}; переписано={rewrites}")

    lines = ["# Прогон вопросов к чату Аристеи", ""]
    for name, r in cols:
        lines.append(f"* {name}: {_meta(r['meta'])}")
    lines += ["", "Нарушение — ответ, где проверка кодом что-то нашла. Совпадения по словам "
              "приблизительны: смотреть фрагмент глазами.", ""]

    head = "| # | Вопрос | Тема |" + "".join(f" {n}: нарушений |" for n, _ in cols)
    lines += [head, "|---|---|---|" + "---|" * len(cols)]
    for i, item in enumerate(cur["items"]):
        cells = "".join(f" {_count(r['items'][i])} |" for _, r in cols)
        topic = item["topic"] if not base else f"{base['items'][i]['topic']} → {item['topic']}"
        lines.append(f"| {item['id']} | {item['q']} | {topic} |{cells}")
    totals = "".join(f" {sum(_count(x) for x in r['items'])} |" for _, r in cols)
    tokens = "".join(f" {sum(a['prompt_tokens'] for x in r['items'] for a in x['answers'])} |" for _, r in cols)
    rewrites = "".join(f" {sum(a.get('gender_rewrites', 0) for x in r['items'] for a in x['answers'])} |" for _, r in cols)
    lines += [f"| | **Итого** | |{totals}", f"| | Токенов на прогон | |{tokens}",
              f"| | Фраз переписано (род) | |{rewrites}", ""]

    for i, item in enumerate(cur["items"]):
        lines += ["---", "", f"## {item['id']}. {item['q']}", "", f"Нужно для ответа: {item['needs']}", ""]
        for name, r in cols:
            it = r["items"][i]
            for n, a in enumerate(it["answers"], 1):
                tag = f"{name}" + (f", повтор {n}" if len(it["answers"]) > 1 else "")
                lines += [f"### {tag} (тема: {it['topic']}, {a['checks']['words']} слов, {a['finish_reason']})", ""]
                lines += [f"> {s}" if s else ">" for s in a["text"].splitlines()]
                issues = _issues(a)
                lines += ["", ("**Проверка:** " + "; ".join(issues)) if issues else "**Проверка:** чисто", ""]

    # Промпт целиком — чтобы «не из данных» можно было проверить глазами.
    # Берётся у первого вопроса: у остальных отличаются только фрагменты базы знаний.
    for name, r in cols:
        lines += ["---", "", f"## Промпт ({name}, вопрос 1)", "", "```", r["items"][0]["system"], "```", ""]

    Path(args.out).write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--date", default="")
    r.add_argument("--flag", action="store_true", help="chat_planner_context включён")
    r.add_argument("--tier", default="premium")
    r.add_argument("--repeats", type=int, default=1)
    r.add_argument("--out", required=True)
    rep = sub.add_parser("report")
    rep.add_argument("files", nargs="+", help="стало.json [было.json]")
    rep.add_argument("--out", required=True)
    args = p.parse_args()
    if args.cmd == "run":
        asyncio.run(run(args))
    else:
        report(args)


if __name__ == "__main__":
    main()
