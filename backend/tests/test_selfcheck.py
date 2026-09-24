"""Самопроверка прогнозов и сигналы владельцу (backend/selfcheck.py, backend/forecast/stats.py).

Проверяется то, ради чего всё писалось: запасной текст, вчерашняя дата и
пустая лента — КРАСНЫЕ, хотя снаружи всё «работает»; и один сигнал на
инцидент, а не каждый час.
"""
from __future__ import annotations

import asyncio
import sys
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from backend import selfcheck as S
from backend.forecast import stats

TODAY = date(2026, 9, 24)

# Ответ модели, проходящий проверку: образец без «сегодня» (как в test_forecast.py).
from backend.forecast.prompts import DAILY_SAMPLE  # noqa: E402

GOOD_DAILY = DAILY_SAMPLE.replace("Сегодня хороший день", "Хороший день").replace("начни его сегодня", "начни его")


class FakeRedis:
    """Ровно те команды, что зовут selfcheck и stats."""

    def __init__(self):
        self.kv: dict = {}
        self.h: dict = {}

    def set(self, k, v, nx=False, ex=None):
        if nx and k in self.kv:
            return None
        self.kv[k] = v
        return True

    def delete(self, k):
        return 1 if self.kv.pop(k, None) is not None else 0

    def exists(self, k):
        return int(k in self.kv)

    def hincrby(self, k, f, n):
        self.h.setdefault(k, {})
        self.h[k][f] = self.h[k].get(f, 0) + n

    def expire(self, k, ttl):
        pass

    def hgetall(self, k):
        return dict(self.h.get(k, {}))

    def pipeline(self):
        return _Pipe(self)


class _Pipe:
    def __init__(self, r):
        self.r, self.ops = r, []

    def __getattr__(self, name):
        return lambda *a, **k: self.ops.append((name, a, k))

    def execute(self):
        return [getattr(self.r, n)(*a, **k) for n, a, k in self.ops]


class Outbox:
    def __init__(self, ok=True):
        self.sent, self.ok = [], ok

    async def __call__(self, text):
        self.sent.append(text)
        return self.ok


# ── Самопроверка краснеет там, где снаружи всё «работает» ────

GOOD_DAY = {"date": TODAY.isoformat(), "source": "model", "paragraphs": ["Спокойный день."]}


def test_forecast_day_green():
    assert S.problem_forecast_day(GOOD_DAY, TODAY) is None


def test_forecast_day_red_on_fallback():
    assert "запасной" in S.problem_forecast_day({**GOOD_DAY, "source": "fallback"}, TODAY)


def test_forecast_day_red_on_yesterday():
    yesterday = (TODAY - timedelta(days=1)).isoformat()
    assert yesterday in S.problem_forecast_day({**GOOD_DAY, "date": yesterday}, TODAY)


def test_forecast_day_red_on_empty_text():
    assert S.problem_forecast_day({**GOOD_DAY, "paragraphs": ["  "]}, TODAY)


def test_lunation_red_on_fallback_green_on_model():
    good = {"source": "model", "headline": "Полнолуние в Овне", "actions": ["Подведи итог."]}
    assert S.problem_lunation(good) is None
    assert S.problem_lunation({**good, "source": "fallback"})
    assert S.problem_lunation({**good, "headline": ""})


def test_feed_red_on_empty():
    assert "пустая" in S.problem_feed({"events": []})


def test_feed_red_without_lunar_events():
    assert "лунных" in S.problem_feed({"events": [{"kind": "transit"}]})


def test_feed_green_with_moon_house():
    assert S.problem_feed({"events": [{"kind": "transit"}, {"kind": "planner_moon_house"}]}) is None


def test_planner_red_on_other_month_and_error():
    good = {"month_title": "Планер на Сентябрь 2026", "month_sections": [{}]}
    from backend.transit.planner_engine import _month_name
    good["month_title"] = f"Планер на {_month_name(TODAY)}"
    assert S.problem_planner(good, TODAY) is None
    assert S.problem_planner(good, TODAY + timedelta(days=31))
    assert S.problem_planner({"error": "нет"}, TODAY)


def test_step_exception_is_a_failure(monkeypatch):
    async def boom(*a):
        raise RuntimeError("сломалось")

    monkeypatch.setattr(S, "build_chart", lambda: object())
    monkeypatch.setitem(S.STEPS, "feed", boom)
    out = asyncio.run(S.run_steps(["feed"]))
    assert "сломалось" in out["feed"]


# ── Один сигнал на инцидент ─────────────────────────────────

def test_one_signal_per_incident_and_one_recovery():
    r, box = FakeRedis(), Outbox()
    run = lambda p: asyncio.run(S.settle(r, "feed", p, send=box))  # noqa: E731

    assert run("лента пустая") == "opened"
    assert run("лента пустая") is None
    assert run("лента всё ещё пустая") is None
    assert len(box.sent) == 1 and box.sent[0].startswith("🔴")

    assert run(None) == "resolved"
    assert run(None) is None
    assert len(box.sent) == 2 and box.sent[1].startswith("✅")


def test_unsent_signal_is_retried_not_lost():
    r = FakeRedis()
    asyncio.run(S.settle(r, "feed", "пусто", send=Outbox(ok=False)))
    box = Outbox()
    assert asyncio.run(S.settle(r, "feed", "пусто", send=box)) == "opened"
    assert len(box.sent) == 1


def test_daily_run_twice_signals_once(monkeypatch):
    r, box = FakeRedis(), Outbox()

    async def steps(names):
        return {n: ("отдан запасной текст" if n == "forecast_day" else None) for n in names}

    monkeypatch.setattr(S, "run_steps", steps)
    monkeypatch.setattr("backend.notifications.telegram.send_support_message", box)
    asyncio.run(S.run_daily(r))
    asyncio.run(S.run_daily(r))
    assert len(box.sent) == 1 and "прогноз на день" in box.sent[0]


# ── Часовая проверка ────────────────────────────────────────

@pytest.fixture
def hourly(monkeypatch):
    """Состояние сервиса по умолчанию — здоровое; тест меняет нужное."""
    state = {"key": "k", "spent": 1.0, "limit": 10.0, "counts": {}, "probe": None, "steps": []}
    box = Outbox()
    monkeypatch.setattr("backend.config.get_settings",
                        lambda: SimpleNamespace(deepseek_api_key=state["key"]))
    monkeypatch.setattr(S, "budget_state", lambda: (state["spent"], state["limit"]))
    monkeypatch.setattr(stats, "read_window", lambda **k: state["counts"])

    async def probe():
        return state["probe"]

    async def steps(names):
        state["steps"].append(list(names))
        return {n: None for n in names}

    monkeypatch.setattr(S, "probe_model", probe)
    monkeypatch.setattr(S, "run_steps", steps)
    monkeypatch.setattr("backend.notifications.telegram.send_support_message", box)
    state["box"] = box
    return state


def test_hourly_healthy_is_silent(hourly):
    asyncio.run(S.run_hourly(FakeRedis()))
    assert hourly["box"].sent == []


def test_no_key_signals_without_any_traffic(hourly):
    hourly["key"] = ""
    asyncio.run(S.run_hourly(FakeRedis()))
    assert any("ключ" in m for m in hourly["box"].sent)


def test_budget_out_signals_without_any_traffic(hourly):
    hourly["spent"] = 10.0
    asyncio.run(S.run_hourly(FakeRedis()))
    assert any("бюджет исчерпан" in m for m in hourly["box"].sent)


def test_budget_low_below_twenty_percent(hourly):
    hourly["spent"] = 8.5
    asyncio.run(S.run_hourly(FakeRedis()))
    assert len(hourly["box"].sent) == 1 and "на исходе" in hourly["box"].sent[0]


def test_model_down_signals_once_then_recovers(hourly):
    r = FakeRedis()
    hourly["probe"] = "HTTP 402: Insufficient Balance"
    asyncio.run(S.run_hourly(r))
    asyncio.run(S.run_hourly(r))
    hourly["probe"] = None
    asyncio.run(S.run_hourly(r))
    sent = hourly["box"].sent
    assert len(sent) == 2 and "402" in sent[0] and sent[1].startswith("✅")


def test_red_steps_are_rerun_hourly(hourly):
    r = FakeRedis()
    r.set(S._INCIDENT_PREFIX + "feed", "пусто")
    asyncio.run(S.run_hourly(r))
    assert hourly["steps"] == [["feed"]]
    assert any("Починилось" in m and "лента" in m for m in hourly["box"].sent)


@pytest.mark.parametrize("model,fallback,red", [
    (0, 9, False),    # меньше 10 прогнозов — не судим
    (7, 3, True),     # 30 %
    (8, 2, False),    # ровно 20 % — ещё норма
])
def test_fallback_share_threshold(model, fallback, red):
    s = stats.summarize({"today:model": model, "today:fallback:model_error": fallback})
    assert bool(S.problem_fallback_share(s)) is red


# ── Счётчики ────────────────────────────────────────────────

@pytest.fixture
def fake_stats_redis(monkeypatch):
    r = FakeRedis()
    monkeypatch.setattr(stats.interpretation_cache, "_redis", r)
    return r


def test_stats_window_is_sliding_24h(fake_stats_redis):
    now = datetime(2026, 9, 24, 12, tzinfo=timezone.utc)
    stats.incr("today:model", now=now)
    stats.incr("today:model", now=now - timedelta(hours=23))
    stats.incr("today:model", now=now - timedelta(hours=24))   # уже за окном
    assert stats.read_window(now=now) == {"today:model": 2}


def test_selfcheck_chart_not_counted(fake_stats_redis):
    stats.record_outcome(stats.SELFCHECK_CHART_ID, "today", "fallback", "no_key")
    stats.record_outcome("real-chart", "today", "fallback", "no_key")
    assert stats.summarize(stats.read_window())["by_reason"]["no_key"] == 1


def test_forecast_records_reason_and_counts_cache_hits(fake_stats_redis, monkeypatch):
    """Запасной текст пишется с причиной; кэш-хит — как показ из модели."""
    from backend.forecast import router as R
    from backend.models import NatalChart

    chart = NatalChart(
        id="c1", timezone="Europe/Moscow", time_unknown=False,
        planets=[{"name": n, "longitude": lon, "sign": "Aries"} for n, lon in
                 (("Sun", 84.5), ("Moon", 200.3), ("Venus", 45.8), ("Mars", 10.2))],
        houses=[{"number": i + 1, "sign": "Aries", "degree": float(i * 30 + 5)} for i in range(12)],
    )
    replies = ["", GOOD_DAILY]

    async def fake(prompt, **k):
        return replies.pop(0)

    store: dict = {}
    monkeypatch.setattr(R, "_ask_model", fake)
    monkeypatch.setattr(R.interpretation_cache, "get", lambda k: store.get(k))
    monkeypatch.setattr(R.interpretation_cache, "set", lambda k, v, ttl=None: store.__setitem__(k, v))
    monkeypatch.setattr(R, "settings", SimpleNamespace(deepseek_api_key="", ai_daily_budget_usd=10))

    assert asyncio.run(R.daily_forecast(chart, "Europe/Moscow", TODAY))["source"] == "fallback"
    asyncio.run(R.daily_forecast(chart, "Europe/Moscow", TODAY))   # модель ответила
    asyncio.run(R.daily_forecast(chart, "Europe/Moscow", TODAY))   # кэш
    s = stats.summarize(stats.read_window())
    assert s["by_reason"]["no_key"] == 1
    assert s["model"] == 2


# ── Sentry ──────────────────────────────────────────────────

def test_sentry_off_without_dsn(monkeypatch):
    from backend import sentry_setup
    monkeypatch.setitem(sys.modules, "sentry_sdk", None)   # импорт упал бы
    assert sentry_setup.init_sentry("", "api") is False


def test_sentry_scrub_drops_personal_data():
    from backend.sentry_setup import scrub
    event = {
        "user": {"id": "u1", "email": "a@b.ru"},
        "request": {"url": "https://x/api/v1/geo?q=Москва", "query_string": "q=Москва",
                    "data": {"birth_date": "1990-06-15", "birth_place": "Москва"},
                    "env": {"REMOTE_ADDR": "203.0.113.7"},
                    "headers": {"X-Real-IP": "203.0.113.7", "X-Forwarded-For": "203.0.113.7",
                                "User-Agent": "okhttp"}},
        "breadcrumbs": {"values": [
            {"category": "httplib", "data": {"url": "https://nominatim/search?q=Москва", "http.query": "q=Москва"}},
            {"category": "log", "message": "вопрос: что меня ждёт"},
            {"category": "redis", "message": "GET interp:abc"},
        ]},
        "exception": {"values": [{"value": "Email send failed for a@b.ru"}]},
    }
    out = scrub(event)
    flat = repr(out)
    for secret in ("Москва", "1990-06-15", "a@b.ru", "что меня ждёт", "interp:abc", "203.0.113.7"):
        assert secret not in flat, secret
    assert out["breadcrumbs"]["values"][0]["data"]["url"] == "https://nominatim/search"


def test_sentry_scrub_replaces_email_whole():
    """Ни первой буквы, ни домена — на скраббер Sentry не полагаемся."""
    from backend.sentry_setup import scrub
    out = scrub({
        "message": "письмо для owner@example.com",
        "logentry": {"message": "a owner@example.com", "formatted": "b owner@example.com"},
        "extra": {"to": "owner@example.com"},
        "exception": {"values": [{"value": "Email send failed for owner@example.com"}]},
    })
    flat = repr(out)
    assert "@" not in flat and "example.com" not in flat and "o***" not in flat
    assert out["message"] == "письмо для [email]"
    assert out["exception"]["values"][0]["value"] == "Email send failed for [email]"
