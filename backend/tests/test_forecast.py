"""Прогнозы в приложении: на сегодня и на новолуние/полнолуние (backend/forecast/).

Модель подменяется очередью ответов (`_ask_model`): проверяется не качество
текста, а то, что вокруг него — проверка, повтор, запасной текст, кэш,
отсутствие списания `transit_ai`, урезанный режим.
"""
from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, timedelta, timezone

import pytest

from backend.forecast import facts as F
from backend.forecast import router as R
from backend.forecast.fallback import daily_fallback, lunation_fallback
from backend.forecast.prompts import (
    DAILY_SAMPLE, build_daily_prompt, build_lunation_prompt, lunation_allowed, lunation_needs_warning,
)
from backend.forecast.validate import (
    check_daily, check_lunation, date_ru, parse_json_reply, problems_daily,
)
from backend.models import NatalChart

_PLANETS = [
    ("Sun", 84.5), ("Moon", 200.3), ("Mercury", 70.1), ("Venus", 45.8), ("Mars", 10.2),
    ("Jupiter", 110.4), ("Saturn", 295.0), ("Uranus", 278.3), ("Neptune", 284.1), ("Pluto", 226.0),
]


def _chart(db, user, time_unknown=False, planets=_PLANETS) -> NatalChart:
    chart = NatalChart(
        user_id=user.id, birth_date="1990-06-15", birth_time=None if time_unknown else "10:30",
        birth_place="Moscow, Russia", latitude=55.75, longitude=37.62, timezone="Europe/Moscow",
        time_unknown=time_unknown, house_system="placidus",
        planets=[{"name": n, "longitude": lon, "sign": "Aries", "degree_in_sign": lon % 30,
                  "house": 1, "retrograde": False} for n, lon in planets],
        houses=[{"number": i + 1, "sign": "Aries", "degree": float(i * 30 + 5)} for i in range(12)],
        aspects=[], ascendant={"sign": "Aries", "degree": 5.0, "longitude": 5.0},
        midheaven={"sign": "Capricorn", "degree": 5.0, "longitude": 275.0},
    )
    db.add(chart)
    db.commit()
    db.refresh(chart)
    return chart


@pytest.fixture
def model(monkeypatch):
    """Очередь ответов модели + счётчик вызовов. Пустая очередь = модель молчит."""
    state = {"replies": [], "calls": 0}

    async def fake(prompt, *, contour, json_mode, max_tokens):
        state["calls"] += 1
        return state["replies"].pop(0) if state["replies"] else ""

    monkeypatch.setattr(R, "_ask_model", fake)
    store: dict = {}
    monkeypatch.setattr(R.interpretation_cache, "get", lambda k: store.get(k))
    monkeypatch.setattr(R.interpretation_cache, "set", lambda k, v, ttl=None: store.__setitem__(k, v))
    return state


@pytest.fixture
def no_transit_ai(monkeypatch):
    """Любое обращение к квоте transit_ai — провал теста."""
    from backend.auth.rate_limits import tier_limiter

    def boom(*a, **k):
        raise AssertionError("прогноз тронул квоту transit_ai")

    monkeypatch.setattr(tier_limiter, "check_transit_ai_limit", boom)
    monkeypatch.setattr(tier_limiter, "commit_transit_ai", boom)


# ── Проверка текста ─────────────────────────────────────────

NORMAL_PHRASES = [
    "Побудь дома и займись домашними делами.",
    "Дома сегодня уютнее, чем обычно.",
    "В рабочей среде всё спокойно, а к среде станет легче.",
    "Твой выбор — сделать вывод и выдохнуть.",
    "Если выглянет солнце, выйди на прогулку.",
    "Лунный свет вечером располагает к тишине.",
    "Это хороший знак внимания к себе.",
    "Купи наконец кухонные весы.",
    "Рыбы на ужин и ранний сон — отличный план.",
    "Второй раз за неделю не стоит соглашаться на лишнее.",
    "Соединение с близкими людьми сейчас важнее дел.",
]


@pytest.mark.parametrize("phrase", NORMAL_PHRASES)
def test_normal_phrases_pass(phrase):
    assert problems_daily(phrase) == []


FORBIDDEN = [
    "Луна в пятом доме зовёт к творчеству.",
    "Сегодня активен дом 7.",
    "Трин Венеры помогает в делах.",
    "Квадрат с Марсом напряжён.",
    "Луна в Раке делает тебя чувствительнее.",
    "Ты сейчас в знаке Скорпиона.",
    "Меркурий подсказывает, что говорить.",
    "Ваш день будет лёгким.",
    "Вы справитесь.",
    "12 сентября лучше отдохнуть.",
    "Во вторник будет легче.",
    "Натальная карта говорит о переменах.",
    "Транзит усиливает энергию.",
    "Солнце на 10° от точки.",
    "ИИ подсказывает спокойствие.",
]


@pytest.mark.parametrize("phrase", FORBIDDEN)
def test_forbidden_is_caught(phrase):
    assert problems_daily(phrase), phrase


def test_daily_sample_itself_passes():
    """Образец владельца — эталон: проверка обязана его пропускать."""
    paragraphs, problems = check_daily(DAILY_SAMPLE)
    assert problems == [] and len(paragraphs) == 3


def test_parse_json_is_tolerant():
    assert parse_json_reply('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json_reply('Вот ответ: {"a": 1} — готово') == {"a": 1}
    assert parse_json_reply("{сломано") is None
    assert parse_json_reply("") is None


# ── Запасной текст ──────────────────────────────────────────

@pytest.mark.parametrize("facts", [
    F.DayFacts(date(2026, 9, 23), False, "Дева", houses=[4, 5], aspects=[
        {"natal": "Venus", "tone": "harmonious"}, {"natal": "Mars", "tone": "tense"}]),
    F.DayFacts(date(2026, 9, 23), False, "Рыбы", houses=[12], aspects=[]),
    F.DayFacts(date(2026, 9, 23), True, "Овен", houses=[], aspects=[]),
    F.DayFacts(date(2026, 9, 23), True, "Весы", houses=[], aspects=[{"natal": "Sun", "tone": "strong"}]),
])
def test_daily_fallback_is_clean(facts):
    paragraphs = daily_fallback(facts)
    assert 2 <= len(paragraphs) <= 3
    assert problems_daily("\n\n".join(paragraphs)) == []


def _lunation_facts(tense=True, trimmed=False):
    at = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)
    return F.LunationFacts(
        phase="new_moon", at_utc=at, at_local=at.astimezone(F.resolve_tz("Europe/Moscow", None)),
        sign="Весы", trimmed=trimmed, house=None if trimmed else 7,
        aspects=[{"planet": "Mars", "natal": "Venus", "tone": "tense" if tense else "harmonious"}],
        warnings=[{"planet": "Mars", "natal": "Sun", "date": date(2026, 10, 13)}] if tense else [],
    )


@pytest.mark.parametrize("tense", [True, False])
def test_lunation_fallback_passes_check(tense):
    f = _lunation_facts(tense)
    dates, times = lunation_allowed(f)
    _, problems = check_lunation(lunation_fallback(f), dates, times, lunation_needs_warning(f))
    assert problems == []


def test_lunation_without_birth_time_has_no_house():
    f = _lunation_facts(trimmed=True)
    assert "Главная сфера этой фазы" not in build_lunation_prompt(f)
    assert all("Удели особое внимание" not in a for a in lunation_fallback(f)["actions"])


# ── Сегодня: ручка ──────────────────────────────────────────

URL_TODAY = "/api/v1/chart/{}/forecast/today?tz=Europe/Moscow"


def test_today_model_answer_is_served_and_cached(client, db, user_free, auth_headers_free, model, no_transit_ai):
    chart = _chart(db, user_free)
    model["replies"] = [DAILY_SAMPLE]
    first = client.get(URL_TODAY.format(chart.id), headers=auth_headers_free)
    assert first.status_code == 200, first.text
    assert first.json()["source"] == "model"
    second = client.get(URL_TODAY.format(chart.id), headers=auth_headers_free).json()
    assert second == first.json()
    assert model["calls"] == 1, "повторное открытие снова позвало модель"


def test_today_model_down_gives_fallback_not_503(client, db, user_free, auth_headers_free, model, no_transit_ai):
    chart = _chart(db, user_free)
    resp = client.get(URL_TODAY.format(chart.id), headers=auth_headers_free)
    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "fallback"
    assert problems_daily("\n\n".join(body["paragraphs"])) == []


def test_today_bad_answers_retry_then_fallback(client, db, user_free, auth_headers_free, model):
    chart = _chart(db, user_free)
    bad = "Ваш день.\n\nВы справитесь."
    model["replies"] = [bad, DAILY_SAMPLE.replace("Сегодня", "Луна в пятом доме, и сегодня", 1)]
    body = client.get(URL_TODAY.format(chart.id), headers=auth_headers_free).json()
    assert model["calls"] == 2
    assert body["source"] == "fallback"


def test_fallback_is_not_cached(client, db, user_free, auth_headers_free, model):
    chart = _chart(db, user_free)
    client.get(URL_TODAY.format(chart.id), headers=auth_headers_free)
    model["replies"] = [DAILY_SAMPLE]
    body = client.get(URL_TODAY.format(chart.id), headers=auth_headers_free).json()
    assert body["source"] == "model", "запасной текст попал в кэш и заслонил модель"


def test_today_requires_owner(client, db, user_free, auth_headers_pro, model):
    chart = _chart(db, user_free)
    assert client.get(URL_TODAY.format(chart.id), headers=auth_headers_pro).status_code == 404


def test_day_without_aspects_still_has_text(client, db, user_free, auth_headers_free, model):
    chart = _chart(db, user_free, planets=[])
    body = client.get(URL_TODAY.format(chart.id), headers=auth_headers_free).json()
    assert body["paragraphs"] and body["source"] == "fallback"


# ── Урезанный режим ─────────────────────────────────────────

def test_trimmed_day_has_no_houses_and_no_natal_moon(db, user_free):
    chart = _chart(db, user_free, time_unknown=True)
    tz = F.resolve_tz("Europe/Moscow", None)
    for i in range(30):   # Луна обходит карту за месяц — касание к натальной Луне обязательно встретилось бы
        f = F.compute_day(chart, date(2026, 9, 1) + timedelta(days=i), tz)
        assert f.trimmed and f.houses == []
        assert all(a["natal"] != "Moon" for a in f.aspects)


def test_full_day_has_houses_and_sees_natal_moon(db, user_free):
    """Против пустой проверки выше: в полном режиме то же окно даёт и дома,
    и касания к натальной Луне."""
    chart = _chart(db, user_free)
    tz = F.resolve_tz("Europe/Moscow", None)
    days = [F.compute_day(chart, date(2026, 9, 1) + timedelta(days=i), tz) for i in range(30)]
    assert all(d.houses for d in days)
    assert any(a["natal"] == "Moon" for d in days for a in d.aspects)


def test_trimmed_prompt_uses_general_mood():
    f = F.DayFacts(date(2026, 9, 23), True, "Рыбы", houses=[], aspects=[])
    assert "Общий тон дня" in build_daily_prompt(f)


# ── Пояс ────────────────────────────────────────────────────

def test_bad_tz_falls_back_to_chart_tz():
    assert F.resolve_tz("Not/AZone", "Asia/Novosibirsk").key == "Asia/Novosibirsk"
    assert F.resolve_tz(None, "Europe/Moscow").key == "Europe/Moscow"
    assert F.resolve_tz("Asia/Tokyo", "Europe/Moscow").key == "Asia/Tokyo"


# ── Новолуние / полнолуние ─────────────────────────────────

def _next_phase_date(phase: str) -> date:
    """Местная дата ближайшей фазы начиная с 10.10.2026 (find_phase ищет ±2 суток)."""
    for step in range(0, 32, 3):
        at = F.find_phase(phase, date(2026, 10, 10) + timedelta(days=step))
        if at is not None:
            return at.astimezone(F.resolve_tz("Europe/Moscow", None)).date()
    raise AssertionError(f"{phase} не найдена за месяц")


def _lunation_reply(allowed_date: str, warning: bool) -> str:
    return json.dumps({
        "headline": "Сегодня новолуние, а значит новый цикл начинается спокойно.",
        "sign_meaning": "Этот знак про отношения, согласие и красоту.",
        "actions": ["Запиши желание.", "Наведи порядок.", "Составь план.", "Позвони близкому.", "Отдохни."],
        "warning": {"text": f"{allowed_date} возможна спешка.",
                    "tips": ["Не спеши.", "Проверяй факты.", "Береги силы."]} if warning else None,
        "closing": "Семена посажены — дай им время.",
    }, ensure_ascii=False)


def test_lunation_model_answer(client, db, user_free, auth_headers_free, model, no_transit_ai):
    chart = _chart(db, user_free)
    d = _next_phase_date("new_moon")
    model["replies"] = [_lunation_reply(date_ru(d), warning=True)] * 2
    resp = client.get(
        f"/api/v1/chart/{chart.id}/forecast/lunation?phase=new_moon&date={d}&tz=Europe/Moscow",
        headers=auth_headers_free,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["phase"] == "new_moon" and body["actions"]
    # Модели позволено отвечать без warning только при отсутствии напряжения —
    # здесь ответ с warning проходит в любом случае.
    assert body["source"] == "model"


def test_lunation_invented_date_goes_to_fallback(client, db, user_free, auth_headers_free, model):
    chart = _chart(db, user_free)
    d = _next_phase_date("full_moon")
    model["replies"] = [_lunation_reply("31 декабря", warning=True)] * 2
    body = client.get(
        f"/api/v1/chart/{chart.id}/forecast/lunation?phase=full_moon&date={d}&tz=Europe/Moscow",
        headers=auth_headers_free,
    ).json()
    assert body["source"] == "fallback"


def test_lunation_trimmed_has_no_house_and_no_natal_moon(db, user_free):
    chart = _chart(db, user_free, time_unknown=True)
    at = F.find_phase("new_moon", date(2026, 10, 10))
    f = F.compute_lunation(chart, "new_moon", at, F.resolve_tz("Europe/Moscow", None))
    assert f.trimmed and f.house is None
    assert all(a["natal"] != "Moon" for a in f.aspects)


def test_lunation_bad_phase_is_422(client, db, user_free, auth_headers_free, model):
    chart = _chart(db, user_free)
    resp = client.get(
        f"/api/v1/chart/{chart.id}/forecast/lunation?phase=eclipse&date=2026-10-10",
        headers=auth_headers_free,
    )
    assert resp.status_code == 422


# ── Уведомление «daily» ─────────────────────────────────────

@pytest.mark.parametrize("aspect", [None, "trine", "square"])
def test_daily_push_teaser_is_on_ty(monkeypatch, aspect):
    """Тизер утреннего уведомления — на «ты», без терминов и без текста прогноза."""
    from types import SimpleNamespace

    from backend.push import cron

    events = [SimpleNamespace(aspect_type=aspect)] if aspect else []
    monkeypatch.setattr("backend.transit.engine.calculate_transits", lambda **k: events)
    body = cron._daily_body(SimpleNamespace(planets=[]), date(2026, 9, 23))
    assert problems_daily(body) == [], body
    assert "Загляни" in body or "Твой" in body


# ── Расход ──────────────────────────────────────────────────

def test_ask_model_records_deepseek_spend(monkeypatch):
    spent = []
    monkeypatch.setattr(R.settings, "deepseek_api_key", "test")
    monkeypatch.setattr("backend.interpretation.router.track_engine_spend",
                        lambda engine, tokens, contour: spent.append((engine, tokens, contour)))

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": "текст"}}], "usage": {"total_tokens": 1234}}

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            return _Resp()

    monkeypatch.setattr(R.httpx, "AsyncClient", _Client)
    out = asyncio.run(R._ask_model("p", contour="forecast/today", json_mode=False, max_tokens=10))
    assert out == "текст"
    assert spent == [("deepseek", 1234, "forecast/today")]
