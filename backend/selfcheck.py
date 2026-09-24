"""Самопроверка прогнозов и сигналы владельцу: узнать о поломке раньше людей.

Зачем. Запасной текст (`forecast/fallback.py`) спасает человека от пустой
карточки — и тем же самым прячет поломку: снаружи прогноз «работает». У
конкурента прогноз на день был сломан больше года, и никто не заметил.
Поэтому здесь проверяется не «ответ пришёл», а «ответ ИЗ МОДЕЛИ, на ТУ дату».

Два прогона (Beat, `celery_app.py`):

* **утренний, 07:30 МСК** — четыре шага на служебной карте: прогноз на день,
  ближайшая фаза Луны, лента на сегодня, планер на текущий месяц; плюс доля
  👎 за 7 дней (`forecast_feedback`) — сигнал выше 30 % при ≥ 10 оценках.
  Счёт раз в сутки, а не в час: оценок мало, и часовая проверка по недельному
  окну сообщала бы одно и то же весь день;
* **часовой** — ключ и бюджет DeepSeek, пробный запрос к модели, доля
  запасных за сутки, плюс повтор тех утренних шагов, что сейчас красные: так
  «починилось» приходит в течение часа, а не следующим утром.

⚠️ **Служебная карта не хранится нигде** — объект `NatalChart` в памяти, без
пользователя и без строки в БД (решение владельца 24.09.2026). Поэтому её не
нужно прятать из метрик и рассылок: там её просто нет. Прогнозы по ней не
пишутся и в счётчики (`stats.SELFCHECK_CHART_ID`). Цена: авторизация и
маршруты HTTP этим не проверяются — их держат тесты.

⚠️ **Один сигнал на инцидент.** Открытый инцидент — ключ в Redis без TTL;
пока он есть, повторные провалы молчат. Ушло в норму — ключ снимается и
приходит «починилось». Если Telegram не принял сообщение, состояние
откатывается, и попытка повторится через час: иначе инцидент считался бы
объявленным, а владелец о нём не знал бы.

⚠️ **Причины «нет ключа» и «бюджет кончился» сигналят без минимальной выборки**
(решение владельца 24.09.2026): при двух пользователях порог в 10 прогнозов в
сутки не наберётся никогда. Они проверяются по СОСТОЯНИЮ (ключ, потраченное),
а не по счётчику запасных — сигнал придёт и при нуле запросов.

Бюджет обнуляется в полночь по часам сервера (UTC, то есть 03:00 МСК) —
`BudgetTracker._today_key`. Инцидент бюджета в этот момент закроется сам, и это
правда: бюджет действительно снова есть.
"""
from __future__ import annotations

import asyncio
import calendar
import logging
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx

logger = logging.getLogger("astro.selfcheck")

SELFCHECK_TZ = "Europe/Moscow"

# Пороги (решение владельца 24.09.2026).
FALLBACK_SHARE_MAX = 0.20     # доля запасных за сутки, выше — сигнал
FALLBACK_MIN_SAMPLE = 10      # …но только если прогнозов за сутки не меньше
BUDGET_LOW_SHARE = 0.20       # остаток бюджета ниже этой доли — сигнал
DISLIKE_SHARE_MAX = 0.30      # доля 👎 за неделю, выше — сигнал
DISLIKE_MIN_SAMPLE = 10       # …но только если оценок за неделю не меньше
DISLIKE_WINDOW_DAYS = 7

PROBE_TIMEOUT_SEC = 30.0

_INCIDENT_PREFIX = "astro:incident:"

STEP_TITLES = {
    "forecast_day": "Самопроверка: прогноз на день",
    "lunation": "Самопроверка: прогноз на фазу Луны",
    "feed": "Самопроверка: лента на сегодня",
    "planner": "Самопроверка: планер на текущий месяц",
}
TITLES = {
    **STEP_TITLES,
    "no_key": "DeepSeek: не задан ключ",
    "budget_out": "DeepSeek: суточный бюджет исчерпан",
    "budget_low": "DeepSeek: бюджет на исходе",
    "model_down": "DeepSeek: модель недоступна",
    "fallback_share": "Прогнозы: много запасных текстов",
    "dislike_share": "Прогнозы: много 👎",
    # Сверка платежей (payments/reconcile.py). Имена с id платежа после
    # двоеточия — заголовок берётся по части до него.
    "payments_api": "Оплата: сверка с ЮKassa не прошла",
    "payment_no_tier": "Оплата: деньги есть — тарифа нет",
    "payment_credit_failed": "Оплата: сверка не смогла начислить",
}

# Лунные события ленты: проход Луны по дому, фаза, затмение.
_LUNAR_KINDS = ("planner_moon_house", "moon_phase", "eclipse")


# ── Служебная карта ─────────────────────────────────────────

def build_chart():
    """Карта в памяти: Москва, 15.06.1990 10:30. Синхронно (Swiss Ephemeris)."""
    from backend.ephemeris.calculator import calculate_full_chart
    from backend.ephemeris.geo import resolve_utc_datetime
    from backend.forecast.stats import SELFCHECK_CHART_ID
    from backend.models import NatalChart

    lat, lon = 55.7558, 37.6173
    utc_dt, _, _ = resolve_utc_datetime(birth_date="1990-06-15", birth_time="10:30", timezone=SELFCHECK_TZ)
    data, _aspects = calculate_full_chart(utc_dt=utc_dt, latitude=lat, longitude=lon, house_system="placidus")
    return NatalChart(
        id=SELFCHECK_CHART_ID, user_id=None,
        birth_date="1990-06-15", birth_time="10:30", birth_place="Москва",
        latitude=lat, longitude=lon, timezone=SELFCHECK_TZ, utc_datetime=utc_dt,
        time_unknown=False, house_system="placidus",
        planets=[{
            "name": p.name, "longitude": p.longitude, "sign": p.sign,
            "degree_in_sign": p.degree_in_sign, "house": p.house, "retrograde": p.retrograde,
        } for p in data.planets],
        houses=[{"number": h.number, "sign": h.sign, "degree": h.degree} for h in data.houses],
        aspects=[],
        ascendant={"sign": data.ascendant.sign, "degree": data.ascendant.degree, "longitude": data.ascendant.longitude},
        midheaven={"sign": data.midheaven.sign, "degree": data.midheaven.degree, "longitude": data.midheaven.longitude},
    )


# ── Оценка результатов: чистые функции, их и проверяют тесты ────

def problem_forecast_day(result: dict, today: date) -> str | None:
    if result.get("date") != today.isoformat():
        return f"дата прогноза {result.get('date')} вместо {today.isoformat()}"
    if result.get("source") != "model":
        return "отдан запасной текст, а не ответ модели"
    if not any((p or "").strip() for p in result.get("paragraphs") or []):
        return "пустой текст"
    return None


def problem_lunation(result: dict) -> str | None:
    if result.get("source") != "model":
        return "отдан запасной текст, а не ответ модели"
    if not (result.get("headline") or "").strip() or not result.get("actions"):
        return "пустой текст"
    return None


def problem_feed(feed: dict) -> str | None:
    events = feed.get("events") or []
    if not events:
        return "лента на сегодня пустая"
    if not any(e.get("kind") in _LUNAR_KINDS for e in events):
        return "в ленте на сегодня нет лунных событий"
    return None


def problem_planner(result: dict, today: date) -> str | None:
    from backend.transit.planner_engine import _month_name

    if result.get("error"):
        return f"планер вернул ошибку: {result['error']}"
    expected = f"Планер на {_month_name(today)}"
    if result.get("month_title") != expected:
        return f"заголовок «{result.get('month_title')}» вместо «{expected}»"
    if not result.get("month_sections"):
        return "в планере нет периодов"
    return None


# ── Шаги ────────────────────────────────────────────────────

def next_phase(now_utc: datetime) -> tuple[str, datetime] | None:
    """Ближайшая будущая фаза (новолуние или полнолуние). `find_phase` ищет ±2 суток."""
    from backend.forecast.facts import find_phase

    best = None
    for d in range(0, 33, 3):
        near = now_utc.date() + timedelta(days=d)
        for phase in ("new_moon", "full_moon"):
            at = find_phase(phase, near)
            if at and at > now_utc and (best is None or at < best[1]):
                best = (phase, at)
        if best:
            return best
    return None


async def _step_forecast_day(chart, today: date, now_utc: datetime) -> str | None:
    from backend.forecast.router import daily_forecast
    return problem_forecast_day(await daily_forecast(chart, SELFCHECK_TZ, today), today)


async def _step_lunation(chart, today: date, now_utc: datetime) -> str | None:
    from backend.forecast.router import lunation_forecast

    found = await asyncio.to_thread(next_phase, now_utc)
    if found is None:
        return "ближайшая фаза Луны не найдена"
    phase, at = found
    near = at.astimezone(ZoneInfo(SELFCHECK_TZ)).date()
    return problem_lunation(await lunation_forecast(chart, phase, near, SELFCHECK_TZ))


async def _step_feed(chart, today: date, now_utc: datetime) -> str | None:
    from backend.feed.builder import build_feed
    feed = await asyncio.to_thread(
        build_feed, chart=chart, from_date=today, to_date=today, today=today, tier="premium",
    )
    return problem_feed(feed)


async def _step_planner(chart, today: date, now_utc: datetime) -> str | None:
    from backend.transit.planner_engine import build_planner

    month_start = today.replace(day=1)
    month_end = today.replace(day=calendar.monthrange(today.year, today.month)[1])
    result = await asyncio.to_thread(
        build_planner,
        natal_profile={"planets": chart.planets, "houses": chart.houses,
                       "ascendant": chart.ascendant, "midheaven": chart.midheaven},
        from_date=month_start, to_date=month_end, today=today,
        user_timezone=SELFCHECK_TZ, tier="premium",
    )
    return problem_planner(result, today)


STEPS = {
    "forecast_day": _step_forecast_day,
    "lunation": _step_lunation,
    "feed": _step_feed,
    "planner": _step_planner,
}


async def run_steps(names) -> dict[str, str | None]:
    """Выполнить шаги; исключение шага — тоже провал, с его текстом."""
    now_utc = datetime.now(timezone.utc)
    today = now_utc.astimezone(ZoneInfo(SELFCHECK_TZ)).date()
    try:
        chart = await asyncio.to_thread(build_chart)
    except Exception as e:
        logger.exception("selfcheck: служебная карта не построилась")
        return {n: f"служебная карта не построилась: {type(e).__name__}: {e}" for n in names}
    out = {}
    for name in names:
        try:
            out[name] = await STEPS[name](chart, today, now_utc)
        except Exception as e:
            logger.exception("selfcheck: шаг %s упал", name)
            out[name] = f"исключение {type(e).__name__}: {e}"
    return out


# ── Состояние сервиса ───────────────────────────────────────

async def probe_model() -> str | None:
    """Пробный запрос на 1 токен. `/v1/models` для этого не годится: при
    закончившихся деньгах он зелёный, а генерация отвечает 402."""
    from backend.forecast.router import BUDGET_ENGINE, DEEPSEEK_URL, settings

    try:
        async with httpx.AsyncClient(timeout=PROBE_TIMEOUT_SEC) as client:
            resp = await client.post(
                DEEPSEEK_URL,
                headers={"Authorization": f"Bearer {settings.deepseek_api_key}"},
                json={"model": settings.deepseek_model_pro, "max_tokens": 1, "stream": False,
                      "messages": [{"role": "user", "content": "ok"}],
                      "thinking": {"type": "disabled"}},
            )
    except Exception as e:
        return f"{type(e).__name__}: {e}"
    if resp.status_code != 200:
        return f"HTTP {resp.status_code}: {resp.text[:200]}"
    try:
        data = resp.json()
        data["choices"][0]
    except Exception:
        return "ответ без choices"
    from backend.interpretation.router import track_engine_spend
    track_engine_spend(BUDGET_ENGINE, (data.get("usage") or {}).get("total_tokens") or 0, "selfcheck/probe")
    return None


def budget_state() -> tuple[float, float]:
    from backend.cache import budget_tracker
    from backend.config import get_settings
    return budget_tracker.get_spent(), get_settings().ai_daily_budget_usd


def problem_fallback_share(summary: dict) -> str | None:
    total = summary["total"]
    if total < FALLBACK_MIN_SAMPLE:
        return None
    share = summary["fallback"] / total
    if share <= FALLBACK_SHARE_MAX:
        return None
    return f"запасных {share:.0%} (порог {FALLBACK_SHARE_MAX:.0%})"


def stats_line(summary: dict, spent: float, limit: float) -> str:
    r = summary["by_reason"]
    return (
        f"За 24 ч: из модели {summary['model']}, запасных {summary['fallback']} "
        f"(нет ключа {r['no_key']}, бюджет {r['budget']}, ошибка модели {r['model_error']}, "
        f"отбракованы {r['rejected']}); отбраковано ответов {summary['rejected_answers']} "
        f"(из них по тону {summary['rejected_tone']}), "
        f"ошибок DeepSeek {summary['deepseek_errors']}. Бюджет: ${spent:.2f} из ${limit:.2f}."
    )


# ── 👍/👎 под прогнозами (forecast_feedback, 059) ─────────────

def read_feedback(*, now: datetime | None = None) -> dict | None:
    """{source: {"up": n, "down": n}} за последние 7 суток. Нет базы — None:
    молчим, а не объявляем «оценок ноль» (о базе скажут другие проверки)."""
    from sqlalchemy import func
    from backend.database import SessionLocal
    from backend.models import ForecastFeedback

    since = (now or datetime.now(timezone.utc)).replace(tzinfo=None) - timedelta(days=DISLIKE_WINDOW_DAYS)
    out = {s: {"up": 0, "down": 0} for s in ("model", "fallback")}
    try:
        db = SessionLocal()
        try:
            rows = (db.query(ForecastFeedback.source, ForecastFeedback.rating, func.count())
                    .filter(ForecastFeedback.updated_at >= since)
                    .group_by(ForecastFeedback.source, ForecastFeedback.rating).all())
        finally:
            db.close()
    except Exception as e:
        logger.warning("selfcheck: оценки не прочитаны: %s", e)
        return None
    for source, rating, n in rows:
        if source in out:
            out[source]["up" if rating > 0 else "down"] += n
    return out


def problem_dislike_share(fb: dict) -> str | None:
    """Порог — на все оценки вместе; разбивка по источнику — в тексте сигнала."""
    down = sum(v["down"] for v in fb.values())
    total = down + sum(v["up"] for v in fb.values())
    if total < DISLIKE_MIN_SAMPLE or down / total <= DISLIKE_SHARE_MAX:
        return None
    return f"👎 {down / total:.0%} из {total} оценок за {DISLIKE_WINDOW_DAYS} дн. (порог {DISLIKE_SHARE_MAX:.0%})"


def feedback_line(fb: dict) -> str:
    m, f = fb["model"], fb["fallback"]
    return (f"Оценки за {DISLIKE_WINDOW_DAYS} дн.: модель 👍 {m['up']} 👎 {m['down']}, "
            f"запасные 👍 {f['up']} 👎 {f['down']}.")


# ── Инциденты ───────────────────────────────────────────────

async def settle(redis, name: str, problem: str | None, *, send=None, details: str = "") -> str | None:
    """Свести провал/норму к сигналу. Возвращает 'opened' | 'resolved' | None."""
    if send is None:
        from backend.notifications.telegram import send_support_message as send
    key = _INCIDENT_PREFIX + name
    title = TITLES.get(name) or TITLES.get(name.split(":")[0], name)
    try:
        if problem:
            if not redis.set(key, problem, nx=True):
                return None
            text = f"🔴 {title}\n{problem}" + (f"\n{details}" if details else "")
            if not await send(text):
                redis.delete(key)
                return None
            return "opened"
        if not redis.delete(key):
            return None
        if not await send(f"✅ Починилось: {title}"):
            redis.set(key, "ожидает сообщения «починилось»")
            return None
        return "resolved"
    except Exception as e:
        logger.warning("selfcheck: инцидент %s не обработан: %s", name, e)
        return None


def _is_open(redis, name: str) -> bool:
    try:
        return bool(redis.exists(_INCIDENT_PREFIX + name))
    except Exception:
        return False


# ── Прогоны ─────────────────────────────────────────────────

async def run_daily(redis) -> dict:
    results = await run_steps(list(STEPS))
    for name, problem in results.items():
        await settle(redis, name, problem)
    fb = read_feedback()
    if fb is not None:
        results["dislike_share"] = problem_dislike_share(fb)
        await settle(redis, "dislike_share", results["dislike_share"], details=feedback_line(fb))
    return results


async def run_hourly(redis) -> dict:
    from backend.config import get_settings
    from backend.forecast import stats

    out: dict[str, str | None] = {}
    has_key = bool(get_settings().deepseek_api_key)
    spent, limit = budget_state()
    summary = stats.summarize(stats.read_window())
    details = stats_line(summary, spent, limit)
    fb = read_feedback()
    if fb is not None:
        details += "\n" + feedback_line(fb)

    out["no_key"] = None if has_key else "DEEPSEEK_API_KEY пуст — все прогнозы уходят в запасной текст"
    out["budget_out"] = (
        f"потрачено ${spent:.2f} из ${limit:.2f} — прогнозы уходят в запасной текст"
        if spent >= limit else None
    )
    out["budget_low"] = (
        f"осталось ${max(limit - spent, 0):.2f} из ${limit:.2f} (порог {BUDGET_LOW_SHARE:.0%})"
        if limit - spent < limit * BUDGET_LOW_SHARE else None
    )
    # Без ключа или без бюджета пробный запрос ничего не скажет о самой модели:
    # это состояние уже названо выше, а model_down оставляем как было.
    if has_key and spent < limit:
        out["model_down"] = await probe_model()
    out["fallback_share"] = problem_fallback_share(summary)

    for name, problem in out.items():
        await settle(redis, name, problem, details=details)

    reopen = [n for n in STEPS if _is_open(redis, n)]
    if reopen:
        results = await run_steps(reopen)
        for name, problem in results.items():
            await settle(redis, name, problem)
        out.update(results)
    return out
