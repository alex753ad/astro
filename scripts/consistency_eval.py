"""Прогон согласованности разделов: одна дата, одна карта — одни события.

Шаг 1 плана аудита (docs/audit_unified_model.md, раздел 7), только расчётная
часть, без модели. Запускается из .github/workflows/consistency.yml.

    python scripts/consistency_eval.py run --date 2026-10-03 --days 7 --out a.json [--sky on]
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
  cA  ASC/MC главного события = chart.ascendant/midheaven (по системам домов);
  cB  транзит-аспект: начало, касания и конец одни во всех разделах — лента,
      главное событие и письмо, чат, разбор, PDF, /transits — против своей
      истины (truth_transits; шаг 4 аудита, раздел 8.4).

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
    "cB": "Одно событие — одни границы и касания во всех разделах",
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
_RU_DATE = re.compile(r"(\d{1,2}) (\w+) (\d{4})")


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
        elif cur is not None and line.startswith("Период влияния: "):
            # cB: «Период влияния: 4 октября 2027 — 18 октября 2027» (_format_date_ru).
            cur["period"] = tuple(date(int(y), _MONTHS_RU.index(mo) + 1, int(d))
                                  for d, mo, y in _RU_DATE.findall(line))
    return out


def check_c3(ch: Check, chat_chart: dict, chart_id: str, days: list[date], tzs: list[str],
             chart=None) -> None:
    from backend import day_event
    from backend.day_event import points
    from backend.feed.builder import _naive_utc_to_local_iso, _transit_chunk, _tz, transit_cards
    from backend.interpretation.rag import build_transits_block

    # Под флагом (`run --sky on`, задание 4.4) лента — карточки-касания ядра:
    # сравнение с ними, а не со старым чанком, иначе c3 проверял бы не ту ленту.
    sky = chart is not None and day_event._sky_on(chart)

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
            if sky:
                cards = [c for c in transit_cards(chart, it["exact"] - timedelta(days=45),
                                                  it["exact"] + timedelta(days=45), _tz(tz), "premium")
                         if (c["meta"]["transit_planet"], c["meta"]["natal_planet"], c["meta"]["aspect_type"]) == key]
                shown = min((c["at"][:10] for c in cards),
                            key=lambda s: abs(date.fromisoformat(s) - it["exact"]), default=None)
                ch.ok(shown == it["exact"].isoformat(),
                      f"{d} {tz}: {key} — чат {it['exact']}, лента {shown or 'события нет'}")
                continue
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


# ── cB: одно событие — одни границы (шаг 4 аудита, раздел 8.4) ───────────────

CB_DAYS = 90         # окно событий ленты, главного события, разбора
CB_PDF_MONTHS = 12   # горизонт PDF «Главные транзиты» у Ориона (sections.PLANS)
CB_PDF_N = 10
# Запас скана истины за края окна, дни, и шаг, часы: проход, начатый раньше,
# должен попасть в скан целиком, иначе его начало неизвестно (start_known).
# Медленные — до 2,5 лет одного прохода с петлями (Плутон).
_CB_MARGIN = {"Moon": 3, "Sun": 15, "Mercury": 120, "Venus": 150, "Mars": 240}
_CB_STEP = {"Moon": 1, "Sun": 6, "Mercury": 6, "Venus": 6, "Mars": 6}
_CB_MONTHS = ("января", "февраля", "марта", "апреля", "мая", "июня", "июля",
              "августа", "сентября", "октября", "ноября", "декабря")


def _dmy(d) -> str:
    # С годом: события cB тянутся годами («начало 10.02» без года двусмысленно).
    return d.strftime("%d.%m.%y")


def _wrap(x: float) -> float:
    return (x + 180.0) % 360.0 - 180.0


def truth_transits(points: list[dict], t0: datetime, t1: datetime) -> list[dict]:
    """Истина cB — события «транзит-аспект» с настоящими границами. Свой
    расчёт, а не ядро и не разделы (приём c5/c6): иначе ядро шага 4.1 сверялось
    бы само с собой.

    Касание — смена знака разности долгот `(t − n) ∓ угол`, а не минимум орба
    (станция в 1,6° от точки — не касание). Вход и выход — порог TRANSIT_ORBS.
    Обе границы и касания — бисекция до минуты. Петля — одно событие: следующий
    проход склеивается, если планета вошла в орб с той стороны, с которой
    вышла (развернулась); новый цикл входит с другой стороны.

    `t0`, `t1` — наивный UTC. → [{key, start, end, start_known, end_known,
    touches}], времена aware UTC; события, пересекающие [t0, t1].
    """
    from backend.day_event import counts
    from backend.ephemeris.aspects import ASPECTS
    from backend.ephemeris.calculator import PLANETS, _calc_planet_position, _datetime_to_jd
    from backend.transit.engine import TRANSIT_ORBS

    def lon(pid, t):
        return _calc_planet_position(pid, round(_datetime_to_jd(t), 6))[0]

    def bis(pred, a, b):  # pred(a) != pred(b) → первая минута, где pred как у b
        pa = pred(a)
        while b - a > timedelta(minutes=1):
            m = a + (b - a) / 2
            a, b = (m, b) if pred(m) == pa else (a, m)
        return b

    utc = lambda t: t.replace(tzinfo=timezone.utc)
    out = []
    for tp, pid in PLANETS.items():
        if tp == "North Node":
            continue
        margin, step = timedelta(days=_CB_MARGIN.get(tp, 900)), timedelta(hours=_CB_STEP.get(tp, 24))
        times = [t0 - margin]
        while times[-1] < t1 + margin:
            times.append(times[-1] + step)
        lons = [lon(pid, t) for t in times]
        for p in points:
            for asp, ang in ASPECTS.items():
                if not counts(p["name"], asp):
                    continue
                orb = TRANSIT_ORBS[asp]
                for side in ((1,) if ang in (0, 180) else (1, -1)):
                    shift = p["longitude"] + side * ang
                    f = lambda t: _wrap(lon(pid, t) - shift)
                    v = [_wrap(x - shift) for x in lons]
                    passes, cur = [], None
                    for i, x in enumerate(v):
                        inside = abs(x) <= orb
                        if inside and cur is None:
                            cur = {"start": times[0], "start_known": i > 0, "in": 0}
                            if i:
                                cur["start"] = bis(lambda t: abs(f(t)) <= orb, times[i - 1], times[i])
                                cur["in"] = 1 if v[i - 1] > 0 else -1
                        elif not inside and cur is not None:
                            cur["end"] = bis(lambda t: abs(f(t)) <= orb, times[i - 1], times[i])
                            cur["end_known"], cur["out"] = True, (1 if x > 0 else -1)
                            passes.append(cur)
                            cur = None
                    if cur is not None:
                        passes.append({**cur, "end": times[-1], "end_known": False, "out": 0})
                    roots = [bis(lambda t: f(t) > 0, times[i], times[i + 1])
                             for i in range(len(v) - 1)
                             if (v[i] > 0) != (v[i + 1] > 0) and abs(v[i]) < 90]
                    events = []
                    for ps in passes:
                        if events and ps["in"] and ps["in"] == events[-1]["out"]:
                            events[-1].update(end=ps["end"], end_known=ps["end_known"], out=ps["out"])
                        else:
                            events.append(dict(ps))
                    for e in events:
                        if e["end"] < t0 or e["start"] > t1:
                            continue
                        out.append({
                            "key": (tp, p["name"], asp),
                            "start": utc(e["start"]), "end": utc(e["end"]),
                            "start_known": e["start_known"], "end_known": e["end_known"],
                            "touches": [utc(r) for r in roots if e["start"] <= r <= e["end"]],
                        })
    return out


def _ru_dates(text: str, default_year: int | None = None) -> list[date]:
    """«22 ноября 2026», «13 марта» (год — `default_year`) → даты по порядку."""
    out = []
    for d, mo, y in re.findall(r"(\d{1,2}) (\w+)(?: (\d{4}))?", text):
        if mo in _CB_MONTHS and (y or default_year):
            out.append(date(int(y or default_year), _CB_MONTHS.index(mo) + 1, int(d)))
    return out


def _cb_name(key) -> str:
    from backend.ephemeris.ru_names import ASPECT_RU, PLANET_RU
    tp, np_, asp = key
    return f"{PLANET_RU.get(tp, tp)} {ASPECT_RU.get(asp, asp)} {PLANET_RU.get(np_, np_)}"


_CB_SECTIONS = ("лента", "главное событие", "чат", "разбор", "PDF", "/transits")


def cb_breakdown(bad: list[str]) -> str:
    """Расхождения cB — числами по разделам, у ленты и по причине (задание
    4.4: «сколько ушло у ленты и почему» видно из лога). Только счётчики:
    строки с событиями и датами — в отчёт владельцу, не в публичный лог."""
    sec = {s: 0 for s in _CB_SECTIONS}
    why = {"нет карточки": 0, "касания нет": 0, "другой день": 0}
    for x in bad:
        body = x.split(": ", 1)[-1]
        name = next((s for s in _CB_SECTIONS if body.startswith(s)), "прочее")
        sec[name] = sec.get(name, 0) + 1
        if name == "лента":
            why["другой день" if "другой день" in body else
                "касания нет" if body.endswith("касания нет") else "нет карточки"] += 1
    return ", ".join(f"{k}={v}" for k, v in sec.items()) + " | лента: " + ", ".join(f"{k}={v}" for k, v in why.items())


def check_cB(ch: Check, chart, chat_chart: dict, truth: list[dict], d0: date, days: list[date],
             tz: str, tier: str) -> None:
    """Одно событие — одни границы и касания во всех разделах (п. 8.4 аудита).

    Сравнение — местные даты в поясе `tz`: то, что читает человек. Одна
    строка сравнения — (событие, раздел, пояс); в строке расхождения все
    разошедшиеся поля. Граница, упёршаяся в край скана истины, не сравнивается.
    """
    from backend import day_event
    from backend.chart_points import planets as natal_planets
    from backend.feed.builder import _tz, transit_cards
    from backend.interpretation.rag import build_transits_block
    from backend.pdf_reports.sections import main_transits
    from backend.transit.engine import calculate_transits, compute_exact_facts

    zone = ZoneInfo(tz)
    ld = lambda t: t.astimezone(zone).date()
    d1 = d0 + timedelta(days=CB_DAYS)
    touch_days = {(e["key"], ld(t)) for e in truth for t in e["touches"]}

    def event_on(key, d):
        return next((e for e in truth if e["key"] == key and ld(e["start"]) <= d <= ld(e["end"])), None)

    def no_touch(key, d) -> str:
        """Нет касания в день d: у прохода касаний нет вовсе (станция рядом
        с точкой) или оно в другой день — тогда ближайшее из истины. До
        05.10.2026 оба случая писались «касания нет», и сдвиг на день
        выглядел как выдуманное касание."""
        e = event_on(key, d)
        near = min((ld(t) for t in e["touches"]), key=lambda t: abs((t - d).days), default=None) if e else None
        return f"касание в другой день (истина {_dmy(near)})" if near else "касания нет"

    def bounds(e, start, end) -> list[str]:
        bad = []
        if start is not None and e["start_known"] and start != ld(e["start"]):
            bad.append(f"начало {_dmy(start)} (истина {_dmy(ld(e['start']))})")
        if end is not None and e["end_known"] and end != ld(e["end"]):
            bad.append(f"конец {_dmy(end)} (истина {_dmy(ld(e['end']))})")
        return bad

    # 1. Лента: каждая карточка транзита — касание из истины, и наоборот.
    # transit_cards — по флагу (`run --sky on`): «как на проде» — старый движок.
    cards = transit_cards(chart, d0, d1, _tz(tz), tier)
    feed_set = {((c["meta"]["transit_planet"], c["meta"]["natal_planet"], c["meta"]["aspect_type"]),
                 date.fromisoformat(c["at"][:10])) for c in cards}
    in_win = {x for x in touch_days if d0 <= x[1] <= d1}
    for key, d in sorted(in_win | feed_set, key=lambda x: (x[1], x[0])):
        if (key, d) not in feed_set:
            ch.ok(False, f"{tz}: лента — касания {_cb_name(key)} {_dmy(d)} нет")
        elif (key, d) not in in_win:
            ch.ok(False, f"{tz}: лента — {_cb_name(key)} {_dmy(d)}: {no_touch(key, d)}")
        else:
            ch.ok(True, "")

    # 2. Главное событие и письмо «Важный транзит» берут касания из _candidates.
    for d in (d0 + timedelta(days=i) for i in range(CB_DAYS + 1)):
        for ev in day_event._candidates(chart, d, zone):
            if ev.natal is None:
                continue
            key = (ev.transit, ev.natal, ev.aspect)
            ch.ok((key, ev.at_local.date()) in touch_days,
                  f"{tz}: главное событие/письмо — {_cb_name(key)} {_dmy(ev.at_local)}: "
                  f"{no_touch(key, ev.at_local.date())}")

    # 3. Чат: «Точный аспект» и «Период влияния» из блока транзитов.
    for d in days:
        for it in parse_chat_block(build_transits_block(chat_chart, 5, d, chart.id, tz)):
            key = (it["transit"], it["natal"], it["aspect"])
            e = event_on(key, d)
            if e is None:
                ch.ok(False, f"{tz}: чат {d} — {_cb_name(key)}: в истине события нет")
                continue
            per = it.get("period") or (None, None)
            bad = bounds(e, *per) if len(per) == 2 else ["период не разобран"]
            if it["exact"] and (key, it["exact"]) not in touch_days:
                bad.append(f"точный {_dmy(it['exact'])}: {no_touch(key, it['exact'])}")
            ch.ok(not bad, f"{tz}: чат {d} — {_cb_name(key)}: " + "; ".join(bad))

    # 4. Разбор транзита: те же факты, что считает ручка
    # (main.interpret_transit_event), от meta.peak_date карточки ленты.
    # Под флагом (4.5) — как ручка: событие ядра по peak_date карточки, один
    # разбор на событие (О5) — сравнивается один раз, и с ВСЕМИ касаниями.
    from backend.transit.engine import interpret_event_facts
    sky = day_event._sky_on(chart)
    profile = {"planets": day_event.points(chart), "houses": [] if chart.time_unknown else chart.houses}
    seen = set()
    for c in cards:
        m = c["meta"]
        key = (m["transit_planet"], m["natal_planet"], m["aspect_type"])
        sf, skey = (interpret_event_facts(chart, *key, date.fromisoformat(m["peak_date"]), tz, sky)
                    if key[0] != "Moon" else (None, None))
        ref = skey or (key, m["peak_date"])
        if key[0] == "Moon" or ref in seen:
            continue
        seen.add(ref)
        shown = date.fromisoformat(c["at"][:10])
        e = event_on(key, shown)
        if e is None:
            continue  # карточки без касания уже посчитаны в п. 1
        if sf:
            f = sf
            got, want = set(f["exact_dates"]), {ld(t).isoformat() for t in e["touches"]}
            if got != want:
                ch.ok(False, f"{tz}: разбор — {_cb_name(key)} {_dmy(shown)}: касания "
                             f"{', '.join(sorted(got))} (истина {', '.join(sorted(want))})")
                continue
        else:
            f = compute_exact_facts(*key, date.fromisoformat(m["peak_date"]), profile)
        if not f.get("period_start"):
            ch.ok(False, f"{tz}: разбор — {_cb_name(key)} {_dmy(shown)}: без фактов")
            continue
        bad = bounds(e, date.fromisoformat(f["period_start"]), date.fromisoformat(f["period_end"]))
        if f.get("exact_date") and (key, date.fromisoformat(f["exact_date"])) not in touch_days:
            exact = date.fromisoformat(f["exact_date"])
            bad.append(f"точный {_dmy(exact)}: {no_touch(key, exact)}")
        ch.ok(not bad, f"{tz}: разбор — {_cb_name(key)} {_dmy(shown)}: " + "; ".join(bad))

    # 5. PDF «Главные транзиты» (тариф с горизонтом CB_PDF_MONTHS).
    horizon = d0 + timedelta(days=round(CB_PDF_MONTHS * 30.44))
    for it in main_transits(day_event.points(chart), d0, CB_PDF_MONTHS, CB_PDF_N):
        key = (it["planet"], it["natal"], it["kind"])
        evs = sorted((e for e in truth if e["key"] == key and ld(e["start"]) <= horizon and ld(e["end"]) >= d0),
                     key=lambda e: e["start"])
        if not evs:
            ch.ok(False, f"{tz}: PDF — {_cb_name(key)}: в истине события нет")
            continue
        when, bad = it["when"], []
        if len(evs) > 1:
            bad.append(f"склеено {len(evs)} события через перерыв")
        ends = _ru_dates(when)
        end_year = ends[-1].year if ends else None
        got = _ru_dates(when, end_year)
        first, last = evs[0], evs[-1]
        if when.startswith("до "):
            if first["start_known"] and ld(first["start"]) > d0:
                bad.append(f"«уже идёт», а начало {_dmy(ld(first['start']))}")
            bad += bounds(last, None, got[-1] if got else None)
        elif "продолжается и после" in when:
            if last["end_known"] and ld(last["end"]) <= horizon:
                bad.append(f"«продолжается», а конец {_dmy(ld(last['end']))}")
        elif len(got) == 2:
            bad += bounds(first, got[0], None) + bounds(last, None, got[1])
        want = sorted({ld(t) for e in evs for t in e["touches"] if d0 <= ld(t) <= horizon})[:3]
        if _ru_dates(it["exact"]) != want:
            bad.append(f"касания {', '.join(map(_dmy, _ru_dates(it['exact']))) or 'нет'} "
                       f"(истина {', '.join(map(_dmy, want)) or 'нет'})")
        ch.ok(not bad, f"{tz}: PDF — {_cb_name(key)}: " + "; ".join(bad))

    # 6. /transits: два соседних окна, как их листает веб; событие обязано
    # иметь одни даты в обоих. Точки — как у ручки (chart_points.planets).
    for w0, w1 in ((d0, d0 + timedelta(days=91)), (d0 + timedelta(days=91), d0 + timedelta(days=182))):
        resp = calculate_transits(natal_planets(chart), w0, w1)
        for e in truth:
            if ld(e["end"]) < w0 or ld(e["start"]) > w1 or e["key"][0] == "Moon":
                continue
            got = [r for r in resp if (r.transit_planet, r.natal_planet, r.aspect_type) == e["key"]
                   and r.start_date <= ld(e["end"]).isoformat() and r.end_date >= ld(e["start"]).isoformat()]
            if not got:
                ch.ok(False, f"{tz}: /transits {_dmy(w0)}–{_dmy(w1)} — {_cb_name(e['key'])}: на вебе нет")
                continue
            for r in got:
                bad = bounds(e, date.fromisoformat(r.start_date), date.fromisoformat(r.end_date))
                peak = date.fromisoformat(r.peak_date)
                if (e["key"], peak) not in touch_days:
                    bad.append(f"пик {_dmy(peak)}: {no_touch(e['key'], peak)}")
                ch.ok(not bad, f"{tz}: /transits {_dmy(w0)}–{_dmy(w1)} — {_cb_name(e['key'])}: " + "; ".join(bad))


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

def _sky_switch(mode: str) -> None:
    """`--sky on` — как у человека с флагом `sky_event` (задание 4.2): разделы
    решают флаг через `day_event._sky_on(chart)`, у карт прогона базы нет —
    подменяется сам ответ. В скрипте базы (до 4.2) переключателя нет: её
    столбец — всегда «как на проде»."""
    if mode == "on":
        from backend import day_event
        day_event._sky_on = lambda chart: True


async def run(args) -> None:
    from chat_eval import _chart
    from backend.interpretation.rag import chat_chart_data

    import logging
    # В лог — только счётчики: модули проекта пишут окна расчёта с датами (INFO)
    # и данные в предупреждениях — логирование проекта в прогоне выключено целиком.
    logging.disable(logging.CRITICAL)
    _sky_switch(args.sky)
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
    guard(checks["c3"], check_c3, checks["c3"], chat_chart_data(stored, time_unknown), "consistency-full", days, tzs,
          _ns(stored, "consistency-full", tzs[0], time_unknown))
    # cB: истина одна на все пояса (UTC), с запасом под горизонт PDF.
    t0 = datetime.combine(d0, time()) - timedelta(days=1)
    from backend.day_event import points
    truth = guard(checks["cB"], truth_transits, points(_ns(stored, "consistency-full", tzs[0], time_unknown)),
                  t0, t0 + timedelta(days=round(CB_PDF_MONTHS * 30.44) + 2))
    if truth is not None:
        for tz in tzs:
            guard(checks["cB"], check_cB, checks["cB"], _ns(stored, "consistency-full", tz, time_unknown),
                  chat_chart_data(stored, time_unknown), truth, d0, days, tz, args.tier)
    try:
        await check_cA(checks["cA"], birth)
    except Exception as e:  # noqa: BLE001
        checks["cA"].error = f"{type(e).__name__}: {e}"

    commit = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
                            capture_output=True, text=True).stdout.strip()
    out = {
        "meta": {"commit": commit, "date": d0.isoformat(), "days": args.days, "tzs": tzs,
                 "tier": args.tier, "time_unknown": time_unknown, "sky": args.sky},
        "checks": {k: c.as_dict(CHECKS[k]) for k, c in checks.items()},
        "morning": morning(stored, time_unknown, days, tzs),
    }
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    # В лог — только счётчики (см. докстринг модуля).
    print(f"commit={commit} days={args.days} tzs={len(tzs)}")
    for k, c in checks.items():
        err = f" ошибка={c.error.split(':')[0]}" if c.error else ""
        print(f"  {k} сравнено={c.compared} расхождений={len(c.bad)}{err}")
    print("  cB по разделам: " + cb_breakdown(checks["cB"].bad))
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
    sky_file = getattr(args, "sky_file", None)
    sky = json.loads(Path(sky_file).read_text(encoding="utf-8")) if sky_file and Path(sky_file).exists() else None
    lines = [failed_line(cur), "", "# Прогон согласованности разделов", "", f"* Стало: {_meta(cur['meta'])}"]
    if base:
        lines.append(f"* Было: {_meta(base['meta'])}")
    lines += ["", "Расхождение — место, где два раздела говорят разное об одном и том же. "
              "Фазы и станции — окно 31 день.", ""]
    head = "| | Проверка |" + (" Было |" if base else "") + " Стало (как на проде) |" + (" Под флагом sky_event |" if sky else "")
    lines += [head, "|---|---|" + ("---|" if base else "") + "---|" + ("---|" if sky else "")]

    def cell(r, k):
        c = r["checks"].get(k)
        if not c:
            return "—"
        if c["error"]:
            return "**ошибка**"
        return f"{len(c['bad'])} из {c['compared']}"

    for k, title in CHECKS.items():
        lines.append(f"| {k} | {title} |" + (f" {cell(base, k)} |" if base else "") + f" {cell(cur, k)} |"
                     + (f" {cell(sky, k)} |" if sky else ""))
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
    if sky:
        lines += sky_section(cur, sky)
    Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")


def sky_section(cur: dict, sky: dict) -> list[str]:
    """Под флагом `sky_event` против «как на проде» (тот же коммит): что ушло и
    что появилось по проверкам, и «Утро» — только изменившиеся строки."""
    out = ["", "## Под флагом sky_event: отличие от «как на проде»", ""]
    for k in CHECKS:
        a, b = cur["checks"].get(k), sky["checks"].get(k)
        if not a or not b or a["error"] or b["error"]:
            continue
        new = [x for x in b["bad"] if x not in set(a["bad"])]
        gone = [x for x in a["bad"] if x not in set(b["bad"])]
        if new or gone:
            out += [f"**{k}:** новых {len(new)}, ушло {len(gone)}."]
            out += [f"* новое: {x}" for x in new[:MAX_LINES]] + [f"* ушло: {x}" for x in gone[:MAX_LINES]] + [""]
    prod = {(r["date"], r["tz"]): r["push"] for r in cur.get("morning") or []}
    rows = [r for r in sky.get("morning") or [] if prod.get((r["date"], r["tz"])) != r["push"]]
    out += ["", "### Утро под флагом", "", f"Изменилось: {len(rows)} из {len(prod)}."]
    if rows:
        out += ["", "| Дата | Пояс | Как на проде | Под флагом |", "|---|---|---|---|"]
        out += [f"| {r['date']} | {r['tz']} | {prod.get((r['date'], r['tz']), '—')} | {r['push']} |" for r in rows]
    return out


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
    r.add_argument("--sky", choices=("on", "off"), default="off", help="флаг sky_event (4.2)")
    rep = sub.add_parser("report")
    rep.add_argument("files", nargs="+", help="стало.json [было.json]")
    rep.add_argument("--out", required=True)
    rep.add_argument("--base-morning", default=None, help="утро базы (подкоманда morning)")
    rep.add_argument("--sky-file", default=None, help="прогон «под флагом» (run --sky on)")
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
