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
    "Дома уютнее, чем обычно.",
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


# Тон: пугающее ловится в любых падежах и формах, и именно как тон — по этому
# признаку router считает отбраковки по тону для самопроверки.
SCARY = [
    "Возможны болезни, будь внимательнее.",
    "Дорога может закончиться аварию избежать трудно.",
    "Не шути со смертью.",
    "Это время опасного дня для решений.",
    "Заболеть легко, одевайся теплее.",
    "Катастрофически не хватит времени.",
    "Ни в коем случае не подписывай бумаги.",
    "Такой исход неизбежен.",
    "Берегись резких слов.",
    "Есть угроза для денег.",
    "Возможна измена.",
    "Травмы вероятнее обычного.",
]


@pytest.mark.parametrize("phrase", SCARY)
def test_scary_words_are_caught_as_tone(phrase):
    from backend.forecast.validate import is_tone_problem
    problems = problems_daily(phrase)
    assert any(is_tone_problem(p) for p in problems), (phrase, problems)


TONE_NORMAL = [
    "Безопасно попробовать что-то новое.",
    "Изменение в планах пойдёт на пользу.",
    "Если что-то не успелось — это не страшно.",
    "Береги себя и ложись пораньше.",
    "Умеренно нагружай себя, и сил хватит.",
    "Рабочий кризис позади, можно выдохнуть.",
    "Забота о здоровье и режим дадут силы.",
    "Изменения в делах к лучшему.",
    "Обида может задеть — не спеши отвечать.",
    "Побеседуй с тем, кто рядом.",
]


@pytest.mark.parametrize("phrase", TONE_NORMAL)
def test_tone_normal_phrases_pass(phrase):
    assert problems_daily(phrase) == [], phrase


def test_tone_applies_to_lunation_too():
    f = _lunation_facts(tense=True)
    dates, times = lunation_allowed(f)
    block = lunation_fallback(f)
    block["closing"] = "Это роковой день, будь осторожнее."
    _, problems = check_lunation(block, dates, times, True)
    assert any(p.startswith("тон: ") for p in problems)


def test_daily_sample_differs_only_by_relative_day_words():
    """Образец владельца — эталон тона: у него единственное расхождение с
    правилами — «сегодня». Слово запрещено с 24.09.2026: текст дня служит
    и «завтра», и «сегодня», и «вчера» (forecast/router.py)."""
    paragraphs, problems = check_daily(DAILY_SAMPLE)
    assert problems == ["сегодня/завтра/вчера"] and len(paragraphs) == 3
    _, neutral = check_daily(GOOD_DAILY)
    assert neutral == []


@pytest.mark.parametrize("phrase", [
    "Сегодня хороший день.", "Завтра будет легче.", "Вчерашние дела подождут.",
])
def test_relative_day_words_are_caught(phrase):
    assert "сегодня/завтра/вчера" in problems_daily(phrase)


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
    # Три дня подряд — это все три варианта каждой фразы.
    for shift in range(3):
        f = F.DayFacts(facts.local_date + timedelta(days=shift), facts.trimmed, facts.moon_sign,
                       houses=facts.houses, aspects=facts.aspects)
        paragraphs = daily_fallback(f)
        assert 2 <= len(paragraphs) <= 3
        assert problems_daily("\n\n".join(paragraphs)) == []


@pytest.mark.parametrize("facts", [
    F.DayFacts(date(2026, 9, 30), False, "Дева", houses=[4], aspects=[{"natal": "Saturn", "tone": "tense"}]),
    F.DayFacts(date(2026, 12, 31), True, "Рыбы", houses=[], aspects=[]),
])
def test_daily_fallback_differs_on_consecutive_days(facts):
    """Одинаковые смыслы два дня подряд (так бывает: касание медленной планеты
    держится днями) — текст всё равно другой, причём КАЖДЫЙ абзац. Даты взяты
    на стыке месяца и года: там день месяца сбрасывается, а выбор — нет."""
    today = daily_fallback(facts)
    nxt = daily_fallback(F.DayFacts(facts.local_date + timedelta(days=1), facts.trimmed,
                                    facts.moon_sign, houses=facts.houses, aspects=facts.aspects))
    assert all(a != b for a, b in zip(today, nxt))
    assert daily_fallback(facts) == today, "повторное открытие в тот же день дало другой текст"


def test_lunation_fallback_differs_between_consecutive_cycles():
    f = _lunation_facts()
    nxt = F.LunationFacts(
        phase=f.phase, at_utc=f.at_utc + timedelta(days=29.53), at_local=f.at_local + timedelta(days=29.53),
        sign=f.sign, trimmed=f.trimmed, house=f.house, aspects=f.aspects, warnings=f.warnings,
    )
    a, b = lunation_fallback(f), lunation_fallback(nxt)
    assert a["headline"] != b["headline"] and a["closing"] != b["closing"]


def _lunation_facts(tense=True, trimmed=False):
    at = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)
    return F.LunationFacts(
        phase="new_moon", at_utc=at, at_local=at.astimezone(F.resolve_tz("Europe/Moscow", None)),
        sign="Весы", trimmed=trimmed, house=None if trimmed else 7,
        aspects=[{"planet": "Mars", "natal": "Venus", "tone": "tense" if tense else "harmonious"}],
        warnings=[{"planet": "Mars", "natal": "Sun", "date": date(2026, 10, 13)}] if tense else [],
    )


@pytest.mark.parametrize("phase", ["new_moon", "full_moon"])
@pytest.mark.parametrize("tense", [True, False])
def test_lunation_fallback_passes_check(tense, phase):
    base = _lunation_facts(tense)
    for cycle in range(3):   # три цикла подряд — все три варианта
        shift = timedelta(days=29.53 * cycle)
        f = F.LunationFacts(
            phase=phase, at_utc=base.at_utc + shift, at_local=base.at_local + shift, sign=base.sign,
            trimmed=base.trimmed, house=base.house, aspects=base.aspects, warnings=base.warnings,
        )
        dates, times = lunation_allowed(f)
        _, problems = check_lunation(lunation_fallback(f), dates, times, lunation_needs_warning(f))
        assert problems == []


def test_lunation_without_birth_time_has_no_house():
    f = _lunation_facts(trimmed=True)
    assert "Главная сфера этой фазы" not in build_lunation_prompt(f)
    assert all("Удели особое внимание" not in a for a in lunation_fallback(f)["actions"])


# ── Сегодня: ручка ──────────────────────────────────────────

def _today_msk() -> date:
    return datetime.now(timezone.utc).astimezone(F.resolve_tz("Europe/Moscow", None)).date()


class _Url:
    """Прогноз на сегодняшнюю дату — через общую ручку /forecast/day."""
    def format(self, chart_id):
        return f"/api/v1/chart/{chart_id}/forecast/day?date={_today_msk()}&tz=Europe/Moscow"


URL_TODAY = _Url()

# Образец владельца с нейтральными словами вместо «сегодня» — годный ответ.
GOOD_DAILY = (
    DAILY_SAMPLE
    .replace("Сегодня хороший день", "Хороший день")
    .replace("начни его сегодня", "начни его")
)


def test_today_model_answer_is_served_and_cached(client, db, user_free, auth_headers_free, model, no_transit_ai):
    chart = _chart(db, user_free)
    model["replies"] = [GOOD_DAILY]
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
    model["replies"] = [bad, GOOD_DAILY.replace("Хороший день", "Луна в пятом доме, и хороший день", 1)]
    body = client.get(URL_TODAY.format(chart.id), headers=auth_headers_free).json()
    assert model["calls"] == 2
    assert body["source"] == "fallback"


def test_fallback_is_not_cached(client, db, user_free, auth_headers_free, model):
    chart = _chart(db, user_free)
    client.get(URL_TODAY.format(chart.id), headers=auth_headers_free)
    model["replies"] = [GOOD_DAILY]
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


# ── Сегодня / завтра (вчера закрыт) ─────────────────────────

def test_allowed_days_open_tomorrow_at_19():
    tz = F.resolve_tz("Europe/Moscow", None)
    before = datetime(2026, 9, 24, 18, 59, tzinfo=tz)
    after = datetime(2026, 9, 24, 19, 0, tzinfo=tz)
    assert R.allowed_days(before) == [date(2026, 9, 24)]
    assert R.allowed_days(after) == [date(2026, 9, 24), date(2026, 9, 25)]


def _day_url(chart_id, d):
    return f"/api/v1/chart/{chart_id}/forecast/day?date={d}&tz=Europe/Moscow"


class TestNoYesterday:
    """Прогноза на вчера нет (решение владельца 24.09.2026): прошлая дата —
    404, а не текст, и модель на неё не зовётся."""

    def test_past_dates_are_404(self, client, db, user_free, auth_headers_free, model):
        chart = _chart(db, user_free)
        today = _today_msk()
        for back in (1, 2):
            r = client.get(_day_url(chart.id, today - timedelta(days=back)), headers=auth_headers_free)
            assert r.status_code == 404
        assert model["calls"] == 0
        assert client.get(_day_url(chart.id, today), headers=auth_headers_free).status_code == 200


def test_cache_key_has_timezone(client, db, user_free, auth_headers_free, model, no_transit_ai):
    """Факты дня считаются в поясе телефона — текст для Москвы не должен
    отдаваться другому поясу. Ключ: карта, местная дата, пояс, версия."""
    chart = _chart(db, user_free)
    model["replies"] = [GOOD_DAILY, GOOD_DAILY]
    # Минск — тот же UTC+3, дата всегда совпадает с московской; пояс другой.
    base = f"/api/v1/chart/{chart.id}/forecast/day?date={_today_msk()}"
    assert client.get(base + "&tz=Europe/Moscow", headers=auth_headers_free).status_code == 200
    assert client.get(base + "&tz=Europe/Minsk", headers=auth_headers_free).status_code == 200
    assert model["calls"] == 2, "второй пояс получил текст первого из кэша"


def test_tomorrow_opens_only_from_19(client, db, user_free, auth_headers_free, model, monkeypatch):
    chart = _chart(db, user_free)
    tomorrow = _today_msk() + timedelta(days=1)
    monkeypatch.setattr(R, "TOMORROW_OPEN_HOUR", 24)   # «ещё не 19:00»
    assert client.get(_day_url(chart.id, tomorrow), headers=auth_headers_free).status_code == 404
    monkeypatch.setattr(R, "TOMORROW_OPEN_HOUR", 0)    # «уже 19:00»
    assert client.get(_day_url(chart.id, tomorrow), headers=auth_headers_free).status_code == 200


def test_old_today_endpoint_is_gone(client, db, user_free, auth_headers_free, model):
    chart = _chart(db, user_free)
    assert client.get(f"/api/v1/chart/{chart.id}/forecast/today",
                      headers=auth_headers_free).status_code == 404


# ── Вечернее уведомление «прогноз на завтра» ────────────────

@pytest.mark.parametrize("quiet_from, expected", [
    ("22:00", (20, 0)),   # обычно — 20:00
    ("21:30", (20, 0)),
    ("21:00", (19, 0)),   # тихие часы до 21:00 — переносим на 19:00
    ("20:00", (19, 0)),
    ("19:30", (19, 0)),
    ("19:00", None),      # с 19:00 и раньше — не шлём
    ("18:00", None),
    ("07:00", (20, 0)),   # бессмысленная пара (раньше утра) — «границы нет»
])
def test_evening_send_time(quiet_from, expected):
    from backend.push.cron import evening_send_time
    assert evening_send_time("08:00", quiet_from) == expected


@pytest.fixture
def pushes(monkeypatch):
    sent = []
    monkeypatch.setattr("backend.push.cron.send_to_user",
                        lambda db, uid, payload: sent.append(payload) or 1)
    return sent


def _at(h, m=0):
    return datetime(2026, 9, 24, h, m, tzinfo=F.resolve_tz("Europe/Moscow", None))


def test_evening_push_once_after_20(db, user_free, pushes):
    from backend.push.cron import _send_evening
    chart = _chart(db, user_free)
    assert _send_evening(db, user_free, chart, _at(19, 30)) == 0
    assert _send_evening(db, user_free, chart, _at(20, 5)) == 1
    assert _send_evening(db, user_free, chart, _at(20, 20)) == 0, "второй раз за вечер"
    assert len(pushes) == 1
    p = pushes[0]
    assert p["target"] == "feed_tomorrow" and p["keys"] == ["tomorrow:2026-09-25"]
    # «завтра» уведомлению можно — оно про завтра; остальные правила те же.
    from backend.forecast.validate import problems_common
    assert problems_common(p["body"]) == [] and problems_common(p["title"]) == []


def test_evening_push_moves_to_19_before_early_quiet(db, user_free, pushes):
    from backend.push.cron import _send_evening
    user_free.push_quiet_from = "21:00"
    db.commit()
    chart = _chart(db, user_free)
    assert _send_evening(db, user_free, chart, _at(19, 5)) == 1


def test_evening_push_not_in_quiet_hours(db, user_free, pushes):
    from backend.push.cron import _send_evening
    user_free.push_quiet_from = "21:00"
    db.commit()
    chart = _chart(db, user_free)
    assert _send_evening(db, user_free, chart, _at(21, 30)) == 0, "пропущенный вечер не догоняем ночью"
    user_free.push_quiet_from = "19:00"
    db.commit()
    assert _send_evening(db, user_free, chart, _at(19, 30)) == 0
    assert pushes == []


def test_evening_push_follows_daily_toggle(db, user_free, pushes):
    from backend.push.cron import _send_evening
    user_free.push_daily_forecast = False
    db.commit()
    chart = _chart(db, user_free)
    assert _send_evening(db, user_free, chart, _at(20, 5)) == 0


def test_upcoming_plans_evening_push(db, user_free):
    """Локальный канал: вечернее уведомление в выдаче со своим временем."""
    from backend.push.cron import collect_upcoming
    _chart(db, user_free)
    out = collect_upcoming(db, user_free, 3)
    evening = [e for e in out["events"] if e["kind"] == "tomorrow"]
    assert evening, "в выдаче нет вечернего уведомления"
    assert all(e["target"] == "feed_tomorrow" and "T20:00:00" in e["at"] for e in evening)


# ── Уведомление «daily» ─────────────────────────────────────

@pytest.mark.parametrize("aspect", [None, "trine", "square"])
def test_daily_push_teaser_is_on_ty(monkeypatch, aspect):
    """Тизер утреннего уведомления — на «ты», без терминов и без текста прогноза."""
    from types import SimpleNamespace

    from backend.push import cron

    events = [SimpleNamespace(aspect_type=aspect)] if aspect else []
    monkeypatch.setattr("backend.transit.engine.calculate_transits", lambda **k: events)
    body = cron._daily_body(SimpleNamespace(planets=[]), date(2026, 9, 23))
    # «Сегодня» уведомлению можно — оно уходит в сам день; запрет на
    # «сегодня/завтра/вчера» касается только текста прогноза.
    from backend.forecast.validate import problems_common
    assert problems_common(body) == [], body
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


# ── 👍/👎 ────────────────────────────────────────────────────

def _vote(client, chart_id, headers, rating=1, **over):
    body = {"kind": "today", "ref": "2026-09-24", "rating": rating, "prompt_version": 4, "source": "model"}
    body.update(over)
    return client.post(f"/api/v1/chart/{chart_id}/forecast/feedback", json=body, headers=headers)


def test_forecast_answer_carries_prompt_version(client, db, user_free, auth_headers_free, model):
    """Версию клиент возвращает вместе с оценкой — без неё оценка не на что лечь."""
    from backend.forecast.prompts import DAILY_PROMPT_VERSION
    chart = _chart(db, user_free)
    body = client.get(URL_TODAY.format(chart.id), headers=auth_headers_free).json()
    assert body["prompt_version"] == DAILY_PROMPT_VERSION


def test_feedback_second_tap_changes_vote(client, db, user_free, auth_headers_free):
    from backend.models import ForecastFeedback
    chart = _chart(db, user_free)
    assert _vote(client, chart.id, auth_headers_free, 1).status_code == 200
    assert _vote(client, chart.id, auth_headers_free, -1, source="fallback").status_code == 200
    rows = db.query(ForecastFeedback).filter_by(chart_id=chart.id).all()
    assert [(r.rating, r.source) for r in rows] == [(-1, "fallback")]
    # Другой прогноз — своя строка.
    _vote(client, chart.id, auth_headers_free, 1, kind="lunation", ref="new_moon:2026-10-10T12:00")
    assert db.query(ForecastFeedback).filter_by(chart_id=chart.id).count() == 2


@pytest.mark.parametrize("over", [{"rating": 0}, {"rating": 2}, {"kind": "week"}, {"source": "x"}, {"ref": ""}])
def test_feedback_cannot_be_removed_or_malformed(client, db, user_free, auth_headers_free, over):
    chart = _chart(db, user_free)
    assert _vote(client, chart.id, auth_headers_free, **{"rating": 1, **over}).status_code == 422


def test_feedback_requires_owner(client, db, user_free, auth_headers_pro):
    chart = _chart(db, user_free)
    assert _vote(client, chart.id, auth_headers_pro, 1).status_code in (403, 404)


def test_feedback_without_version_is_stored_empty(client, db, user_free, auth_headers_free):
    """Текст из офлайн-кэша до появления версии: пишется NULL, а не текущая версия."""
    from backend.models import ForecastFeedback
    chart = _chart(db, user_free)
    assert _vote(client, chart.id, auth_headers_free, -1, prompt_version=None).status_code == 200
    assert db.query(ForecastFeedback).filter_by(chart_id=chart.id).one().prompt_version is None


def test_previous_openings_go_into_prompt(client, db, user_free, auth_headers_free, model, monkeypatch):
    """Начала прошлых дней берутся из кэша той же версии и пояса, ближайший день первым."""
    chart = _chart(db, user_free)
    today = _today_msk()
    for back, text in [(1, "Вчерашнее начало. Дальше."), (2, "Позавчерашнее начало! Дальше.")]:
        R.interpretation_cache.set(R._daily_key(chart.id, today - timedelta(days=back), "Europe/Moscow"),
                                   {"paragraphs": [text, "второй"]})
    seen = []

    async def fake(prompt, **k):
        seen.append(prompt)
        return GOOD_DAILY

    monkeypatch.setattr(R, "_ask_model", fake)
    client.get(URL_TODAY.format(chart.id), headers=auth_headers_free)
    prompt = seen[0]
    assert "Так начинались прогнозы прошлых дней" in prompt
    assert prompt.index("«Вчерашнее начало.»") < prompt.index("«Позавчерашнее начало!»")
    assert "Дальше" not in prompt


def test_no_previous_openings_rule_without_cache():
    f = F.DayFacts(date(2026, 9, 23), False, "Дева", houses=[4], aspects=[])
    assert "прошлых дней" not in build_daily_prompt(f)
