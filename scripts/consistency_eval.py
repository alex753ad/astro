"""Прогон согласованности разделов: одна дата, одна карта — одни события.

Шаг 1 плана аудита (docs/audit_unified_model.md, раздел 7), только расчётная
часть, без модели. Запускается из .github/workflows/consistency.yml.

    python scripts/consistency_eval.py run --date 2026-10-03 --days 7 --out a.json
    python scripts/consistency_eval.py report a.json [b.json] --out report.md

Функции разделов зовутся НАПРЯМУЮ — те же, что у ручек (как в chat_eval).
Где раздел берёт «сегодня» строкой внутри ручки, а не функцией (проверка 7),
выражение повторено здесь со ссылкой на строку — это помечено у проверки.

Проверки (номера — раздел 7 аудита, решения владельца — его шаг 0):
  c1  главное событие дня (пуш, виджет, сторис) есть в ленте;
  c2  главное событие дня — первый факт прогноза дня;
  c3  дата точного аспекта в чате = дата события в ленте;
  c4  периоды планера = периоды ленты (в том же поясе);
  c5  фаза Луны — одна дата во всех разделах;
  c6  станция ретроградности — одна дата;
  c7  «сегодня» одно во всех разделах (00:30 и 23:30 местного);
  c8  без времени рождения — ни натальной Луны, ни ASC/MC, ни домов;
  c9  тон аспекта одинаков во всех источниках;
  cA  ASC/MC главного события = chart.ascendant/midheaven (по системам домов).

Расхождения — ожидаемый результат, а не сбой: скрипт кончается кодом 0 при
любом их числе, ненулевой код — только если упал сам прогон.

⚠️ Репозиторий публичный. Подробности (даты, события, пояса) — только в
отчёте владельцу в Telegram. В лог — одни счётчики по проверкам; ошибка
проверки — именем класса, без текста. Данные рождения — секрет
CHAT_EVAL_BIRTH, не файл.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
import types
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

# EVAL_ROOT — чужой корень: «утро» базы считается кодом базы этим же
# скриптом (подкоманда morning, workflow «Consistency»): в скрипте базы её нет.
ROOT = Path(os.environ.get("EVAL_ROOT") or Path(__file__).resolve().parent.parent).resolve()
# Свой корень первым: при сравнении с прошлым коммитом его копия лежит рядом
# (см. chat_eval.py).
sys.path.insert(0, str(ROOT))
sys.path.insert(1, str(ROOT / "scripts"))

CHECKS = {
    "c1": "Главное событие дня есть в ленте",
    "c2": "Главное событие дня — первый факт прогноза дня",
    "c3": "Дата точного аспекта в чате = дата в ленте",
    "c4": "Периоды планера = периоды ленты",
    "c5": "Фаза Луны: одна дата во всех разделах",
    "c6": "Станция ретроградности: одна дата",
    "c7": "«Сегодня» одно во всех разделах",
    "c8": "Без времени рождения: нет натальной Луны, ASC, MC, домов",
    "c9": "Тон аспекта одинаков во всех источниках",
    "cA": "ASC/MC главного события = chart.ascendant/midheaven",
}
DEFAULT_TZS = "Europe/Moscow,Asia/Vladivostok,America/New_York"
# Окно фаз и станций: за 7 дней их может не быть ни одной.
LUNAR_DAYS = 31
WINDOW = ("08:00", "22:00")  # окно уведомлений по умолчанию (push/cron.py)
# Тон по решению владельца (шаг 0): одна тройка для всех разделов.
TONE_DECIDED = {"trine": "Гармония", "sextile": "Гармония", "square": "Напряжение",
                "opposition": "Напряжение", "conjunction": "Начало"}
_CANON = {"harmonious": "Гармония", "tense": "Напряжение", "new_cycle": "Начало", "strong": "Начало"}
_PHASE_RU = {"new_moon": "новолуние", "full_moon": "полнолуние"}
_ECLIPSE_PHASE = {"solar": "new_moon", "lunar": "full_moon"}


class Check:
    def __init__(self):
        self.compared = 0
        self.bad: list[str] = []
        self.error: str | None = None
        self.notes: list[str] = []  # пояснения к числам, не расхождения

    def ok(self, cond: bool, detail: str) -> None:
        self.compared += 1
        if not cond:
            self.bad.append(detail)

    def as_dict(self, title: str) -> dict:
        return {"title": title, "compared": self.compared, "bad": self.bad,
                "error": self.error, "notes": self.notes}


def guard(ch: Check, fn, *a):
    """Проверка, упавшая с исключением, — ошибка прогона, а не ноль
    расхождений: «0 из 0» выглядело бы как «всё сходится»."""
    try:
        return fn(*a)
    except Exception as e:  # noqa: BLE001 — ошибка одной проверки не роняет остальные
        ch.error = f"{type(e).__name__}: {e}"


# ── карта ─────────────────────────────────────────────────────────────────────

def _ns(stored: dict, chart_id: str, tz: str, time_unknown: bool):
    """Карта в виде NatalChart: то, что читают разделы. Пояс — устройства (как
    подставляет лента, feed/router._with_timezone)."""
    return types.SimpleNamespace(id=chart_id, timezone=tz, time_unknown=time_unknown, **stored)


def _user(tz: str, tier: str):
    return types.SimpleNamespace(
        id="consistency", device_timezone=tz, tier=tier, primary_chart_id=None,
        push_daily_time=WINDOW[0], push_quiet_from=WINDOW[1],
        # False — _collect_candidates не идёт в базу за флагом push_day_event;
        # главное событие проверяется напрямую (main_event).
        push_daily_forecast=False, push_planner=True, push_key_transits=True,
        push_moon_phases=True,
    )


def _profile(stored: dict, time_unknown: bool) -> dict:
    return {**{k: stored[k] for k in ("planets", "houses", "aspects", "ascendant", "midheaven")},
            "time_unknown": time_unknown}


def _dt(iso: str) -> datetime:
    return datetime.fromisoformat(iso)


def _dm(d) -> str:
    return d.strftime("%d.%m")


def _feed(chart, d_from: date, d_to: date, today: date, tier: str) -> list[dict]:
    from backend.feed.builder import build_feed
    now = datetime.combine(today, time(12))
    return build_feed(chart=chart, from_date=d_from, to_date=d_to, today=today, tier=tier, now=now)["events"]


def _feed_phase_type(e: dict) -> str | None:
    if e["kind"] == "moon_phase":
        return e["meta"]["type"]
    if e["kind"] == "eclipse":
        return _ECLIPSE_PHASE.get(e["meta"]["type"])
    return None


# ── проверки ──────────────────────────────────────────────────────────────────

def check_c1_c2(ch1: Check, ch2: Check, chart, feed: list[dict], days: list[date], tz: str) -> dict:
    from backend import day_event
    from backend.forecast.facts import compute_day
    from backend.forecast.meanings import TONE

    events = {}
    for d in days:
        ev = day_event.main_event(chart, d, tz, *WINDOW)
        events[d] = ev
        if ev is None:
            # Не расхождение: в окне уведомлений нет ни касания, ни фазы —
            # пуш, виджет и сторис в такой день говорят о фазе Луны.
            for c in (ch1, ch2):
                c.notes.append(f"{d} {tz}: главного события нет — сравнивать не с чем")
            continue
        what = day_event.title(ev)
        found = False
        for e in feed:
            if abs((_dt(e["at"]) - ev.at_local).total_seconds()) > 60:
                continue
            if ev.natal is None:
                found = found or _feed_phase_type(e) == ev.transit
            elif e["kind"] == "transit":
                m = e["meta"]
                found = found or (m["transit_planet"], m["natal_planet"], m["aspect_type"]) == (
                    ev.transit, ev.natal, ev.aspect)
        ch1.ok(found, f"{d} {tz}: «{what}» — в ленте нет")

        # Первый факт прогноза — facts.main (forecast/prompts._day_meanings
        # ставит его первым пунктом). С шага 5 — любое главное событие, не
        # только Луна (решение владельца 02.10.2026).
        main = compute_day(chart, d, ZoneInfo(tz), *WINDOW).main
        if ev.natal is None:
            good = main == {"phase": ev.transit}
        else:
            good = main is not None and (main.get("transit"), main.get("natal"), main.get("tone")) == (
                ev.transit, ev.natal, TONE[ev.aspect])
        got = (main.get("phase") or f"{main['transit']} → {main['natal']} ({main['tone']})") if main else "нет"
        ch2.ok(good, f"{d} {tz}: главное «{what}», первый факт прогноза: {got}")
    return events


_CHAT_DATE = re.compile(r"Точный аспект: (\d{1,2}) (\w+) (\d{4})")


def parse_chat_block(text: str) -> list[dict]:
    """Блок транзитов чата (rag.build_transits_block) → [{transit, natal,
    aspect, exact}]. Разбор по меткам _build_facts_block (transit/prompts.py)."""
    from backend.ephemeris.ru_names import PLANET_RU
    from backend.transit.prompts import ASPECT_LABELS_RU, _MONTHS_RU

    planet = {v: k for k, v in PLANET_RU.items()}
    aspect = {v: k for k, v in ASPECT_LABELS_RU.items()}
    out, cur = [], None
    for line in text.splitlines():
        if line.startswith("Транзитная планета: "):
            cur = {"transit": planet.get(line[20:].split(",")[0].strip()), "exact": None}
            out.append(cur)
        elif cur is not None and line.startswith("Натальная планета: "):
            cur["natal"] = planet.get(line[19:].split(",")[0].strip())
        elif cur is not None and line.startswith("Аспект: "):
            cur["aspect"] = aspect.get(line[8:].split(",")[0].strip())
        elif cur is not None and (m := _CHAT_DATE.match(line)):
            cur["exact"] = date(int(m[3]), _MONTHS_RU.index(m[2]) + 1, int(m[1]))
    return out


def check_c3(ch: Check, chat_chart: dict, chart_id: str, days: list[date], tzs: list[str]) -> None:
    from backend.day_event import points
    from backend.feed.builder import _naive_utc_to_local_iso, _transit_chunk, _tz
    from backend.interpretation.rag import build_transits_block

    # Набор точек — тот же, что у ленты и чата (чанк ленты кэшируется по
    # карте, без набора в ключе: feed/builder._transit_chunk).
    planets = points(chat_chart)
    # Блок чата — в поясе человека (rag_router передаёт user_tz), поэтому на
    # каждый пояс свой.
    for d, tz in ((d, tz) for d in days for tz in tzs):
        for it in parse_chat_block(build_transits_block(chat_chart, 5, d, chart_id, tz)):
            if it["exact"] is None:
                continue  # чат честно без даты — сравнивать нечего
            key = (it["transit"], it["natal"], it["aspect"])
            near = []
            for k in (-1, 0, 1):
                y, m = it["exact"].year, it["exact"].month + k
                y, m = (y - 1, 12) if m == 0 else (y + 1, 1) if m == 13 else (y, m)
                near += [e for e in _transit_chunk(chart_id, planets, y, m)
                         if (e["transit_planet"], e["natal_planet"], e["aspect_type"]) == key]
            best = min(near, key=lambda e: abs(date.fromisoformat(e["peak_date"]) - it["exact"]), default=None)
            if best is None:
                ch.ok(False, f"{d} {tz}: чат {key} точный {it['exact']} — в ленте события нет")
                continue
            at = (datetime.fromisoformat(best["exact_date"]) if best.get("exact_date")
                  else datetime.combine(date.fromisoformat(best["peak_date"]), time(12)))
            shown = _naive_utc_to_local_iso(at, _tz(tz))[:10]
            ch.ok(shown == it["exact"].isoformat(),
                  f"{d} {tz}: {key} — чат {it['exact']}, лента {shown}")


def _period_ends(s: str) -> tuple[str, str]:
    a, b = s.split(" — ")
    return a[:5], b[:5]


def check_c4(ch: Check, profile: dict, feed: list[dict], today: date, tz: str, tier: str) -> None:
    import calendar
    from backend.transit.planner_engine import build_planner

    first = today.replace(day=1)
    last = today.replace(day=calendar.monthrange(today.year, today.month)[1])
    p = build_planner(natal_profile=profile, from_date=first, to_date=last, today=today,
                      user_timezone=tz, tier=tier, now=datetime.combine(today, time(12)))

    def feed_set(kind, fmt):
        return {(e["meta"]["planet"], e["meta"]["house"], fmt(_dt(e["at"])), fmt(_dt(e["ends_at"])))
                for e in feed if e["kind"] == kind}

    month = feed_set("planner_period", _dm)
    for s in p["month_sections"]:
        for per in s["periods"]:
            a, b = _period_ends(per["period"])
            ch.ok((s["planet"], per["house"], a, b) in month,
                  f"{tz}: {s['planet_name']} в {per['house']} доме — планер {per['period']}, "
                  f"лента {sorted(x[2] + '—' + x[3] for x in month if x[:2] == (s['planet'], per['house']))}")
    long_ = feed_set("planner_longterm", lambda x: x.strftime("%d.%m.%Y"))
    for l in p["longterm"]:
        a, b = l["period"].split(" — ")
        ch.ok((l["planet"], l["house"], a, b) in long_,
              f"{tz}: {l['planet_name']} в {l['house']} доме — планер {l['period']}, "
              f"лента {sorted(x[2] + ' — ' + x[3] for x in long_ if x[:2] == (l['planet'], l['house']))}")
    moon = feed_set("planner_moon_house", lambda x: x.strftime("%d.%m %H:%M"))
    for w in p["week_days"]:
        if not w["house"]:
            continue
        a = w["date"][:5] + w["date"][-6:]
        b = w["time"][:5] + w["time"][-6:]
        ch.ok(("moon", w["house"], a, b) in moon,
              f"{tz}: Луна в {w['house']} доме — планер {a}—{b}, "
              f"лента {sorted(x[2] + '—' + x[3] for x in moon if x[1] == w['house'] and x[2][:5] == a[:5])}")


def _truth_phases(start: date, end: date, tz: str) -> set[tuple[str, date]]:
    from backend.calendar.lunar_engine import _find_phase, _jd, jd_to_utc
    out = set()
    for target, kind in ((0.0, "new_moon"), (180.0, "full_moon")):
        for jd in _find_phase(_jd(start - timedelta(days=2), 0), _jd(end + timedelta(days=2), 24), target):
            d = jd_to_utc(jd).astimezone(ZoneInfo(tz)).date()
            if start <= d <= end:
                out.add((kind, d))
    return out


def check_c5(ch: Check, chart, user, feed: list[dict], start: date, end: date, tz: str) -> None:
    import backend.main as main
    from backend import story_card, widget
    from backend.email_service import week_phase_lines
    from backend.push.cron import _phases_on_local_date

    truth = _truth_phases(start, end, tz)
    months = sorted({(x.year, x.month) for x in (start, end)})
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    inside = lambda s: {x for x in s if start <= x[1] <= end}
    names = {v: k for k, v in _PHASE_RU.items()}
    sources = {
        "лунный календарь (веб, «Ближайшие 30 дней»)": inside({
            (p["type"], date.fromisoformat(p["date"]))
            for y, m in months for p in main._compute_lunar_calendar(y, m, tz)["phases"]}),
        "лента": inside({(t, _dt(e["at"]).date()) for e in feed if (t := _feed_phase_type(e))}),
        "пуш фазы": {(p.type, d) for d in days for p in _phases_on_local_date(d, tz)},
        "дайджест": {("new_moon" if "🌑" in x else "full_moon", date.fromisoformat(x[:10]))
                     for x in week_phase_lines(start, end, tz)},
        "виджет": {(names[n], d) for d in days
                   if (n := widget.day(chart, d, tz, *WINDOW)["phase"]) in names},
        "сторис": {(names[n], d) for d in days if (n := story_card.card(user, chart, d)["phase"]) in names},
    }
    for kind, d in sorted(truth, key=lambda x: x[1]):
        for name, got in sources.items():
            same = {x[1] for x in got if x[0] == kind}
            ch.ok(same == {d}, f"{tz}: {_PHASE_RU[kind]} {d} — {name}: {', '.join(map(str, sorted(same))) or 'нет'}")


def _truth_stations(start: date, end: date, tz: str) -> set[tuple[str, str, date]]:
    """Точный момент станции — смена знака скорости, бисекция до секунды."""
    from backend.ephemeris.calculator import PLANETS
    from backend.transit.house_passages import PLANET_NAMES_RU, RETRO_PLANETS, _speed_at
    out = set()
    t0 = datetime(start.year, start.month, start.day) - timedelta(days=2)
    for planet in RETRO_PLANETS:
        pid, t = PLANETS[planet], t0
        while t < datetime(end.year, end.month, end.day) + timedelta(days=2):
            n = t + timedelta(days=1)
            a, b = _speed_at(pid, t), _speed_at(pid, n)
            if (a < 0) != (b < 0):
                lo, hi = t, n
                while hi - lo > timedelta(seconds=1):
                    mid = lo + (hi - lo) / 2
                    lo, hi = (mid, hi) if (_speed_at(pid, mid) < 0) == (a < 0) else (lo, mid)
                d = hi.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(tz)).date()
                if start <= d <= end:
                    out.add((PLANET_NAMES_RU[planet][1], "start" if b < 0 else "end", d))
            t = n
    return out


def check_c6(ch: Check, profile: dict, feed: list[dict], start: date, end: date, tz: str) -> None:
    from backend.transit.house_passages import compute_upcoming
    truth = _truth_stations(start, end, tz)
    up_end = start + timedelta(days=30)
    sources = {
        "лента": {(e["meta"]["planet"], e["meta"]["status"], _dt(e["at"]).date())
                  for e in feed if e["kind"] == "retrograde"},
        "«Ближайшие 30 дней»": {(u["planet"], u["status"], date.fromisoformat(u["date"]))
                                for u in compute_upcoming(profile, start, user_timezone=tz) if u["kind"] == "station"},
    }
    for planet, status, d in sorted(truth, key=lambda x: x[2]):
        for name, got in sources.items():
            if name.startswith("«") and d > up_end:
                continue
            same = {x[2] for x in got if x[:2] == (planet, status)}
            ch.ok(d in same, f"{tz}: {planet} {status} {d} — {name}: {', '.join(map(str, sorted(same))) or 'нет'}")


def _frozen(instant: datetime):
    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return instant.astimezone(tz) if tz else instant.replace(tzinfo=None)
    return Frozen


def check_c7(ch: Check, chart, user, d0: date, tzs: list[str]) -> None:
    import pytz
    import backend.pdf_reports.build as pdf_build
    import backend.time_utils as tu
    import backend.transit.planner_engine as pe
    from backend.time_utils import user_tz

    for tz in tzs:
        for hm in (time(0, 30), time(23, 30)):
            instant = datetime.combine(d0, hm, ZoneInfo(tz)).astimezone(timezone.utc)
            frozen = _frozen(instant)
            c = types.SimpleNamespace(**{**chart.__dict__, "timezone": "Europe/Moscow"})
            u = types.SimpleNamespace(**{**user.__dict__, "device_timezone": tz})
            # Выражения ручек — с 04.10.2026 все через time_utils.user_tz.
            with mock.patch.object(pe, "datetime", frozen), mock.patch.object(tu, "datetime", frozen):
                got = {
                    "лента, планер (feed/router.py, main.py planner)": pe.now_local(user_tz(tz, u, c)).date(),
                    "прогноз дня (forecast/router.py)": instant.astimezone(ZoneInfo(user_tz(tz, u, c))).date(),
                    "пуши, «Неделя вперёд» (push/cron._process_user)":
                        instant.astimezone(pytz.timezone(user_tz(None, u, c))).date(),
                    "чат (rag_router.rag_chat)": pe.now_local(user_tz(tz, u, c)).date(),
                    "PDF (build.today_for)": pdf_build.today_for(u, c),
                    "письма, /transits (local_today)": tu.local_today(user_tz(None, u, c)),
                    # С шага 6 (04.10.2026): пояс устройства, local_today.
                    "лунный календарь (main.get_lunar_calendar)": tu.local_today(user_tz(tz)),
                }
            for name, day in got.items():
                ch.ok(day == d0, f"{tz} {hm:%H:%M}: {name} — {day}")


def check_c8(ch: Check, stored: dict, chart, user, feed: list[dict], days: list[date], tz: str,
             once: bool, chart_id: str) -> None:
    from backend import day_event
    from backend.forecast.facts import compute_day
    from backend.push.cron import _collect_candidates

    hidden = {"Moon", "Ascendant", "Midheaven"}
    bad_feed = [e for e in feed if (e["kind"] == "transit" and e["meta"]["natal_planet"] in hidden)
                or e["kind"].startswith("planner_")]
    ch.ok(not bad_feed, f"{tz}: лента — {len(bad_feed)} событий с натальной Луной или домами")
    for d in days:
        ev = day_event.main_event(chart, d, tz, *WINDOW)
        ch.ok(not (ev and ev.natal in hidden), f"{d} {tz}: главное событие к {ev and ev.natal}")
        f = compute_day(chart, d, ZoneInfo(tz), *WINDOW)
        main = [f.main] if f.main and "natal" in f.main else []
        ch.ok(not f.houses and all(a["natal"] not in hidden for a in f.aspects + main),
              f"{d} {tz}: прогноз дня — дома {f.houses}, касания {[a['natal'] for a in f.aspects]}")
        cands = _collect_candidates(None, user, chart, d)
        bad = [c["kind"] for c in cands
               if c["kind"] in ("planner", "planner_week", "planner_month", "cusp_approach")
               or ":Moon:" in c["ref"]]
        ch.ok(not bad, f"{d} {tz}: пуши-кандидаты по домам или натальной Луне: {bad}")
    if not once:
        return
    from backend.interpretation.base import InterpretationRequest
    from backend.interpretation.prompts import build_system_prompt
    from backend.interpretation.rag import build_transits_block, chat_chart_data
    from backend.pdf_reports.sections import longterm_section

    longterm = longterm_section(chart, days[0])
    ch.ok(not longterm, f"PDF «Долгосрочные периоды» по полуденным домам: {len(longterm)}")
    prompt = build_system_prompt(InterpretationRequest(natal_profile=_profile(stored, True)))
    ch.ok('"houses"' not in prompt and '"ascendant"' not in prompt,
          "промпт разбора карты: дома и ASC уходят модели")
    cc = chat_chart_data(stored, True)
    ch.ok(not (cc["houses"] or cc["ascendant"] or cc["midheaven"]), "чат: дома или ASC/MC в карте")
    block = build_transits_block(cc, 5, days[0], chart_id)
    ch.ok("Натальная планета: Луна" not in block, "чат: транзит к натальной Луне")


def check_c9(ch: Check, feed: list[dict]) -> None:
    from backend.forecast.meanings import TONE
    from backend.transit.engine import ASPECT_TONE

    for e in feed:
        if e["kind"] != "transit":
            continue
        a = e["meta"]["aspect_type"]
        got = {
            "пуш, виджет, сторис, письмо (ASPECT_TONE)": _CANON[ASPECT_TONE[a]],
            "прогнозы, чат (meanings.TONE)": _CANON[TONE[a]],
            # «Позитивных» отборов в письмах с шага 5 нет: дайджест и онбординг
            # берут главное событие дня, тон — ASPECT_TONE (строка выше).
        }
        wrong = [f"{k}: {v}" for k, v in got.items() if v != TONE_DECIDED[a]]
        ch.ok(not wrong, f"{a} ({TONE_DECIDED[a]}): " + "; ".join(wrong))


async def check_cA(ch: Check, birth: dict) -> None:
    from chat_eval import _chart
    from backend import day_event
    for system in ("placidus", "koch", "equal", "whole_sign"):
        stored, tz, tu = await _chart({**birth, "house_system": system})
        t = {p["name"]: p["longitude"] for p in day_event._targets(_ns(stored, "a", tz, tu))}
        for name, point in (("Ascendant", "ascendant"), ("Midheaven", "midheaven")):
            want = (stored.get(point) or {}).get("longitude")
            if name not in t or want is None:
                ch.ok(False, f"{system}: {name} — в главном событии точки нет")
                continue
            # Только разница: сами долготы — данные карты (репозиторий публичный).
            diff = abs((t[name] - want + 180) % 360 - 180)
            ch.ok(diff < 0.01, f"{system}: {name} — расходится на {diff:.0f}°")


def morning(stored: dict, time_unknown: bool, days: list[date], tzs: list[str]) -> list[dict]:
    """Утренний пуш (main_event: заголовок и совет) по дням и поясам — для
    раздела отчёта «утро: было / стало» (шаг 5, решение владельца 05.10.2026).
    Не проверка: расхождением не считается, только показывается."""
    from backend import day_event
    out = []
    for tz in tzs:
        chart = _ns(stored, "consistency-full", tz, time_unknown)
        for d in days:
            ev = day_event.main_event(chart, d, tz, *WINDOW)
            out.append({"date": d.isoformat(), "tz": tz,
                        "push": f"{day_event.title(ev)} — «{day_event.advice(ev)}»" if ev else "нет события"})
    return out


async def run_morning(args) -> None:
    """Только утро — для базы (EVAL_ROOT=<корень базы>): в её скрипте его нет."""
    from chat_eval import _chart
    import logging
    logging.disable(logging.CRITICAL)
    birth = json.loads(os.environ["CHAT_EVAL_BIRTH"])
    d0 = date.fromisoformat(args.date)
    days = [d0 + timedelta(days=i) for i in range(args.days)]
    stored, _, time_unknown = await _chart(birth)
    tzs = [t.strip() for t in args.tzs.split(",") if t.strip()]
    data = {"morning": morning(stored, time_unknown, days, tzs)}
    Path(args.out).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"morning days={args.days} tzs={len(tzs)}")


# ── прогон ────────────────────────────────────────────────────────────────────

async def run(args) -> None:
    from chat_eval import _chart
    from backend.interpretation.rag import chat_chart_data

    import logging
    # В лог — только счётчики: модули проекта пишут окна расчёта с датами (INFO)
    # и данные в предупреждениях — логирование проекта в прогоне выключено целиком.
    logging.disable(logging.CRITICAL)
    import backend.ephemeris.geo as geo
    # Одно место — один запрос к геокодеру: карт здесь шесть (с временем, без
    # него, четыре системы домов), а Nominatim пускает раз в секунду.
    _geocode, _memo = geo.geocode_place, {}

    async def geocode_once(place):
        if place not in _memo:
            _memo[place] = await _geocode(place)
        return _memo[place]
    geo.geocode_place = geocode_once

    birth = json.loads(os.environ["CHAT_EVAL_BIRTH"])
    d0 =date.fromisoformat(args.date) if args.date else datetime.now(ZoneInfo("Europe/Moscow")).date()
    days = [d0 + timedelta(days=i) for i in range(args.days)]
    lunar_end = d0 + timedelta(days=max(args.days, LUNAR_DAYS) - 1)
    tzs = [t.strip() for t in args.tzs.split(",") if t.strip()]
    stored, _birth_tz, time_unknown = await _chart(birth)
    nt_stored, _, _ = await _chart({k: v for k, v in birth.items() if k != "time"})
    checks = {k: Check() for k in CHECKS}

    # Окно ленты накрывает месяц планера И неделю его Луны (с понедельника):
    # проход, кончившийся до начала окна, лента не отдаст, а планер покажет.
    month_first = min(d0.replace(day=1), d0 - timedelta(days=d0.weekday()))
    for i, tz in enumerate(tzs):
        user = _user(tz, args.tier)
        full = _ns(stored, "consistency-full", tz, time_unknown)
        notime = _ns(nt_stored, "consistency-notime", tz, True)
        feed = _feed(full, min(month_first, d0 - timedelta(days=1)), lunar_end + timedelta(days=1), d0, args.tier)
        guard(checks["c1"], check_c1_c2, checks["c1"], checks["c2"], full, feed, days, tz)
        checks["c2"].error = checks["c2"].error or checks["c1"].error  # одна функция на обе
        if not time_unknown:
            guard(checks["c4"], check_c4, checks["c4"], _profile(stored, False), feed, d0, tz, args.tier)
            guard(checks["c6"], check_c6, checks["c6"], _profile(stored, False), feed, d0, lunar_end, tz)
        guard(checks["c5"], check_c5, checks["c5"], full, user, feed, d0, lunar_end, tz)
        nt_feed = _feed(notime, d0, days[-1], d0, args.tier)
        guard(checks["c8"], check_c8, checks["c8"], nt_stored, notime, user, nt_feed, days, tz, i == 0,
              "consistency-notime")
        if i == 0:
            guard(checks["c9"], check_c9, checks["c9"], [e for e in feed if d0 <= _dt(e["at"]).date() <= days[-1]])
            guard(checks["c7"], check_c7, checks["c7"], full, user, d0, tzs)
    guard(checks["c3"], check_c3, checks["c3"], chat_chart_data(stored, time_unknown), "consistency-full", days, tzs)
    try:
        await check_cA(checks["cA"], birth)
    except Exception as e:  # noqa: BLE001
        checks["cA"].error = f"{type(e).__name__}: {e}"

    commit = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
                            capture_output=True, text=True).stdout.strip()
    out = {
        "meta": {"commit": commit, "date": d0.isoformat(), "days": args.days, "tzs": tzs,
                 "tier": args.tier, "time_unknown": time_unknown},
        "checks": {k: c.as_dict(CHECKS[k]) for k, c in checks.items()},
        "morning": morning(stored, time_unknown, days, tzs),
    }
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    # В лог — только счётчики (см. докстринг модуля).
    print(f"commit={commit} days={args.days} tzs={len(tzs)}")
    for k, c in checks.items():
        err = f" ошибка={c.error.split(':')[0]}" if c.error else ""
        print(f"  {k} сравнено={c.compared} расхождений={len(c.bad)}{err}")
    # Упавшая проверка — провал прогона (workflow краснеет после отправки
    # отчёта); расхождения — нет.
    if any(c.error for c in checks.values()):
        sys.exit(1)


# ── отчёт ─────────────────────────────────────────────────────────────────────

MAX_LINES = 60


def _meta(m: dict) -> str:
    return (f"коммит {m['commit']}, с {m['date']} на {m['days']} дн., пояса {', '.join(m['tzs'])}, "
            f"тариф {m['tier']}")


def failed_line(run: dict) -> str:
    """Первая строка отчёта и подпись в Telegram: какие проверки не выполнились."""
    failed = [k for k, c in run["checks"].items() if c.get("error")]
    if not failed:
        return "Все проверки выполнились."
    return "⚠️ Не выполнились: " + ", ".join(
        f"{k} ({run['checks'][k]['error'].split(':')[0]})" for k in failed) + "."


def report(args) -> None:
    runs = [json.loads(Path(p).read_text(encoding="utf-8")) for p in args.files]
    cur, base = runs[0], (runs[1] if len(runs) > 1 else None)
    lines = [failed_line(cur), "", "# Прогон согласованности разделов", "", f"* Стало: {_meta(cur['meta'])}"]
    if base:
        lines.append(f"* Было: {_meta(base['meta'])}")
    lines += ["", "Расхождение — место, где два раздела говорят разное об одном и том же. "
              "Фазы и станции — окно 31 день.", ""]
    head = "| | Проверка |" + (" Было |" if base else "") + " Стало |"
    lines += [head, "|---|---|" + ("---|" if base else "") + "---|"]

    def cell(r, k):
        c = r["checks"].get(k)
        if not c:
            return "—"
        if c["error"]:
            return "**ошибка**"
        return f"{len(c['bad'])} из {c['compared']}"

    for k, title in CHECKS.items():
        lines.append(f"| {k} | {title} |" + (f" {cell(base, k)} |" if base else "") + f" {cell(cur, k)} |")
    for k, title in CHECKS.items():
        c = cur["checks"][k]
        lines += ["", f"## {k}. {title}", ""]
        if c["error"]:
            # Ни «расхождений нет», ни сравнения с базой: проверка не выполнилась.
            lines += [f"**Проверка не выполнилась:** `{c['error']}`"]
            continue
        notes = c.get("notes") or []
        if notes:
            lines += [f"Без сравнения: {len(notes)}."] + [f"* {n}" for n in notes[:MAX_LINES]] + [""]
        bad = c["bad"]
        if base and k in base["checks"]:
            old = set(base["checks"][k]["bad"])
            new = [b for b in bad if b not in old]
            gone = [b for b in base["checks"][k]["bad"] if b not in set(bad)]
            lines.append(f"Новых: {len(new)}, ушло: {len(gone)}.")
            lines += [f"* новое: {b}" for b in new[:MAX_LINES]] + [f"* ушло: {b}" for b in gone[:MAX_LINES]]
        else:
            lines += [f"* {b}" for b in bad[:MAX_LINES]] or [
                "Расхождений нет." if c["compared"] else "Сравнивать было нечего (0 сравнений)."]
            if len(bad) > MAX_LINES:
                lines.append(f"* … и ещё {len(bad) - MAX_LINES}")
    lines += morning_section(cur.get("morning"), getattr(args, "base_morning", None))
    Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")


def morning_section(cur: list[dict] | None, base_file: str | None) -> list[str]:
    """«Утро: было / стало» — утренний пуш по дням и поясам."""
    if not cur:
        return []
    base = {}
    if base_file and Path(base_file).exists():
        base = {(r["date"], r["tz"]): r["push"]
                for r in json.loads(Path(base_file).read_text(encoding="utf-8"))["morning"]}
    changed = sum(1 for r in cur if base and base.get((r["date"], r["tz"])) != r["push"])
    out = ["", "## Утро: было / стало", ""]
    out.append(f"Изменилось: {changed} из {len(cur)}." if base else "Базы нет — только «стало».")
    out += ["", "| Дата | Пояс | Было | Стало |", "|---|---|---|---|"]
    for r in cur:
        old = base.get((r["date"], r["tz"]), "—")
        mark = " **≠**" if base and old != r["push"] else ""
        out.append(f"| {r['date']} | {r['tz']} | {old} | {r['push']}{mark} |")
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--date", default="")
    r.add_argument("--days", type=int, default=7)
    r.add_argument("--tzs", default=DEFAULT_TZS)
    r.add_argument("--tier", default="premium")
    r.add_argument("--out", required=True)
    rep = sub.add_parser("report")
    rep.add_argument("files", nargs="+", help="стало.json [было.json]")
    rep.add_argument("--out", required=True)
    rep.add_argument("--base-morning", default=None, help="утро базы (подкоманда morning)")
    m = sub.add_parser("morning")
    m.add_argument("--date", required=True)
    m.add_argument("--days", type=int, default=7)
    m.add_argument("--tzs", default=DEFAULT_TZS)
    m.add_argument("--out", required=True)
    args = p.parse_args()
    if args.cmd == "run":
        asyncio.run(run(args))
    elif args.cmd == "morning":
        asyncio.run(run_morning(args))
    else:
        report(args)


if __name__ == "__main__":
    main()
