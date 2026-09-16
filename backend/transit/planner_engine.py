"""backend/transit/planner_engine.py

Планер без ИИ — все интерпретации берутся из словарей.
Принимает precomputed_periods из house_passages.compute_planner_periods()
и возвращает готовую структуру для фронтенда.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from backend.transit.house_passages import (
    compute_planner_periods,
    PLANET_NAMES_RU,
)

# Методичка «планета × дом» — единственный источник текстов планера.
# Грузится один раз при импорте модуля (модульный кэш), диск больше не трогаем.
_METHODOLOGY_PATH = Path(__file__).parent / "methodology.json"
with open(_METHODOLOGY_PATH, encoding="utf-8") as _f:
    METHODOLOGY: dict = json.load(_f)


def _house_entry(planet_eng: str, house: int) -> dict:
    return METHODOLOGY.get(planet_eng, {}).get("houses", {}).get(str(int(house)), {})


def _planet_lead(planet_eng: str) -> str:
    return METHODOLOGY.get(planet_eng, {}).get("meta", {}).get("lead", "")


def _locked_payload() -> dict:
    """Заблокированный период — на клиент не уходит ни одной строки методички."""
    return {"theme": "", "groups": []}


# ── Тарифные предикаты: что закрыто в планере ────────────────────────────────
#
# Вынесены из build_planner() под ленту (backend/feed/) — той нужны РОВНО те же
# правила, а второй их экземпляр разъехался бы с этим при первой же правке
# сетки. build_planner ниже зовёт эти же функции, поведение не изменилось.
#
# ⚠️ Этих правил НЕТ в TIER_FLAGS и искать их там бесполезно: там лежит
# `planner_months` — горизонт (какой месяц вообще разрешено запросить,
# проверяется в main.py через planner_offset_window). Что закрыто ВНУТРИ
# разрешённого месяца — только здесь.

def is_month_period_locked(tier: Optional[str], planet_key: str, is_current: bool) -> bool:
    """Период быстрой планеты в месячных секциях.

    E1 (Free-витрина): у Free открыт ровно один период — текущий период
    Солнца. Он и продаёт остальные: человек видит формат разбора на своём
    настоящем периоде, а не на примере.
    """
    return tier == "free" and not (planet_key == "sun" and is_current)


def now_local(user_timezone: Optional[str]) -> datetime:
    """«Сейчас» в поясе карты, наивное — тем же видом, что границы проходов.

    Границы прохода приходят наивным местным ISO (`_moon_passages_between`,
    house_passages.py). Сравнивать их с aware-датой нельзя — Python бросит
    TypeError, а сравнивать с UTC можно, но это тихо сдвинет «завершён» на
    величину пояса: в Москве проход, кончившийся в 02:00, три часа считался бы
    будущим.
    """
    if user_timezone:
        try:
            import pytz
            return datetime.now(pytz.timezone(user_timezone)).replace(tzinfo=None)
        except Exception:
            pass
    return datetime.now()


def is_moon_week_locked(
    tier: Optional[str],
    start_iso: Optional[str] = None,
    end_iso: Optional[str] = None,
    now: Optional[datetime] = None,
) -> bool:
    """Закрыт ли ОДИН проход Луны по дому (решение владельца 16.09.2026).

    Правило целиком:

      * **завершённый проход открыт ВСЕМ тарифам** — конец раньше «сейчас».
        Это витрина, а не щедрость: человек видит объём того, что прошло мимо,
        на своих настоящих данных, а не на примере. Прошлое не продаётся —
        ровно та же логика, по которой горизонт ленты назад одинаков у всех
        (backend/feed/horizon.py);
      * **вперёд — по тарифу**, `planner_weeks_ahead` недель, СЧИТАЯ текущую
        (free 1, платные 4).

    ⚠️ Принадлежность к неделе считается по НАЧАЛУ прохода против конца
    последней разрешённой недели, а не «в какую неделю попадает проход». Проход
    Луны по дому длится ~2.3 суток и регулярно пересекает границу недель:
    начался в субботу — кончился во вторник. Считай мы по календарным суткам,
    один и тот же проход был бы одновременно открыт и закрыт. Поэтому граница
    проходит ПО ПРОХОДАМ: начался внутри разрешённого окна — открыт целиком,
    со своим настоящим концом за его пределами.

    Без дат (`start_iso`/`end_iso` не переданы) остаётся прежнее поведение
    «закрыто на free» — на нём стоят вызовы, которым проход неизвестен.
    """
    from backend.auth.rate_limits import TIER_FLAGS

    weeks = TIER_FLAGS.get(tier or "free", TIER_FLAGS["free"]).get("planner_weeks_ahead", 1)

    if not start_iso or not end_iso:
        return tier == "free"

    moment = now or datetime.now()
    try:
        start_dt = datetime.fromisoformat(start_iso)
        end_dt = datetime.fromisoformat(end_iso)
    except ValueError:
        return tier == "free"

    if end_dt < moment:
        return False  # завершившийся проход открыт всем

    # Конец последней разрешённой недели: воскресенье 23:59 недели
    # (текущая + weeks − 1). weeks >= 1 всегда, поэтому текущая неделя открыта
    # у любого тарифа.
    monday = (moment - timedelta(days=moment.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0,
    )
    allowed_end = monday + timedelta(weeks=max(1, weeks)) - timedelta(minutes=1)
    return start_dt > allowed_end


def is_longterm_locked(tier: Optional[str]) -> bool:
    """Долгосрочные транзиты — открыты с Pro и выше, то есть закрыты и на Lite."""
    return tier not in ("pro", "premium")


def _unlocked_payload(planet_eng: str, house: int) -> dict:
    """Полный набор текстов дома дословно из methodology.json.

    theme/groups — всегда. subtitle/notes — только если есть в файле
    (Уран/Нептун/Плутон), для остальных планет ключи не добавляются.
    """
    entry = _house_entry(planet_eng, house)
    payload = {
        "theme": entry.get("theme", ""),
        "groups": [
            {"heading": g.get("heading", ""), "items": list(g.get("items", []))}
            for g in entry.get("groups", [])
        ],
    }
    if "subtitle" in entry:
        payload["subtitle"] = entry["subtitle"]
    if "notes" in entry:
        payload["notes"] = list(entry["notes"])
    return payload


# Маппинг planet_key (lowercase) → английское название (ключи methodology.json)
_KEY_TO_ENG = {
    "sun":     "Sun",
    "mercury": "Mercury",
    "venus":   "Venus",
    "mars":    "Mars",
    "jupiter": "Jupiter",
    "saturn":  "Saturn",
    "uranus":  "Uranus",
    "neptune": "Neptune",
    "pluto":   "Pluto",
}


def build_planner(
    natal_profile: dict,
    from_date: date,
    to_date: date,
    today: Optional[date] = None,
    user_timezone: Optional[str] = None,
    tier: Optional[str] = None,
    week_offset: Optional[int] = None,
    now: Optional[datetime] = None,
) -> dict:
    """Собрать планер полностью в Python без ИИ.

    Возвращает структуру совместимую с PlannerPage.jsx:
    {
      month_title, month_sections, week_title, week_days,
      longterm_title, longterm
    }

    E1 (Free-витрина): при tier="free" полный разбор (items) в МЕСЯЧНЫХ
    секциях остаётся только у текущего периода Солнца; прочие периоды
    возвращаются с items=[] и locked=true (текст на клиент не уходит).
    ⚠️ Луна под это правило больше не подпадает — у недели с 16.09.2026 своя
    сетка, см. ниже.

    Тарифная сетка по разделам:
      Месяц       — открыт с Lite и выше (locked только на Free).
      Неделя      — с 16.09.2026 открыта ВСЕМ: завершившиеся проходы всем,
                    вперёд `planner_weeks_ahead` недель считая текущую
                    (free 1, платные 4). Правило целиком — is_moon_week_locked.
      Долгосрочно — открыт только с Pro и выше (locked на Free и Lite).
    """
    if today is None:
        today = date.today()

    periods = compute_planner_periods(
        natal_profile=natal_profile,
        from_date=from_date,
        to_date=to_date,
        today=today,
        user_timezone=user_timezone,
        week_offset=week_offset,
    )

    month_title = f"Планер на {_month_name(from_date)}"

    # ── month_sections: быстрые планеты ──────────────────────────────────────
    month_sections = []
    for p in periods.get("fast_planets", []):
        eng = _KEY_TO_ENG.get(p["planet_key"], "")
        sections_periods = []
        for period in p.get("periods", []):
            house = period.get("house")
            if not house:
                continue
            # E1: у Free разблокирован только текущий период Солнца
            locked = is_month_period_locked(tier, p["planet_key"], period.get("is_current", False))
            sections_periods.append({
                "period": period["period"],
                "house":  house,
                "locked": locked,
                **(_locked_payload() if locked else _unlocked_payload(eng, house)),
            })
        month_sections.append({
            "planet":          p["planet_key"],
            "planet_name":     p["planet_name"],
            "emoji":           p["emoji"],
            "planet_subtitle": _planet_lead(eng),
            "periods":         sections_periods,
        })

    # ── week_days: луна ───────────────────────────────────────────────────────
    # moon_week теперь содержит периоды нахождения Луны в доме (не дни недели).
    # date  = "21.05 Чт 03:22"  (момент входа в дом)
    # time  = "до 25.05 Пн 01:03"  (момент выхода из дома)
    # house = номер дома
    week_days = []
    # «Сейчас» считается ОДИН раз на весь ответ: внутри цикла соседние проходы
    # могли бы получить разные моменты отсчёта и на стыке недели разъехаться по
    # доступу. Тот же приём, что у `today_dt` выше.
    #
    # ⚠️ Параметр `now` существует не ради тестов одних. Гейт недели — про
    # МОМЕНТ («проход завершился»), а весь остальной планер считает от даты
    # `today`, которую передаёт вызывающий. В проде они совпадают, но передав
    # прошлый `today` и не передав `now`, можно получить ответ, где периоды
    # посчитаны на одну дату, а доступ к ним — на другую. Явный параметр
    # делает это видимым, а не случайным.
    week_now = now or now_local(user_timezone)
    for passage in periods.get("moon_week", []):
        house = passage.get("house", 0)
        locked = is_moon_week_locked(
            tier, passage.get("start_dt"), passage.get("end_dt"), week_now,
        )
        week_days.append({
            "date":  passage["date"],
            "time":  passage.get("time", ""),
            "house": house,
            "locked": locked,
            **(_locked_payload() if (locked or not house)
               else _unlocked_payload("Moon", house)),
        })

    # ── longterm: медленные планеты — открыто только с Pro (сетка тарифов) ────
    longterm = []
    for p in periods.get("slow_planets", []):
        eng = _KEY_TO_ENG.get(p["planet_key"], "")
        house = p.get("house", 0)
        locked = is_longterm_locked(tier)
        longterm.append({
            "planet":          p["planet_key"],
            "planet_name":     p["planet_name"],
            "emoji":           p["emoji"],
            "planet_subtitle": _planet_lead(eng),
            "house":           house,
            "period":          p.get("period_label", ""),
            "locked":          locked,
            **(_locked_payload() if locked else _unlocked_payload(eng, house)),
        })

    return {
        "month_title":    month_title,
        "month_sections": month_sections,
        "week_title":     "Транзитная Луна по домам",
        "week_days":      week_days,
        "week_nav":       periods.get("week_nav"),
        "longterm_title": "Долгосрочные транзиты",
        "longterm":       longterm,
        "retrogrades":    periods.get("retrogrades", []),
    }


_MONTHS_RU = [
    "", "январь", "февраль", "март", "апрель", "май", "июнь",
    "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь",
]

def _month_name(d: date) -> str:
    return f"{_MONTHS_RU[d.month]} {d.year}"
