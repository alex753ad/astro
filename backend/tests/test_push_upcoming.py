"""GET /api/v1/push/upcoming — будущие уведомления для планирования на устройстве.

Плюс две вещи, которые эта ручка обязана унаследовать от веб-пушей, а не
завести заново: окно отправки (обе границы) и запрет на дату границы транзита
в тексте.

⚠️ Тесты ходят через `collect_upcoming`/`_collect_candidates` напрямую там, где
проверяется форма данных, и через HTTP там, где проверяется доступ и валидация.
Причина та же, что в test_feed.py: расчёт эфемерид дорогой, гонять его через
клиента лишний раз незачем.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta

import pytest
import pytz

from backend.models import NatalChart, User
from backend.push.cron import (
    _collect_candidates,
    _process_user,
    collect_upcoming,
    in_send_window,
    UPCOMING_MAX_DAYS,
)


# Натальная карта с фиксированными долготами — по образцу test_feed.py.
# Числа настоящие быть не обязаны, но обязаны быть постоянными: иначе тест
# про «в тексте нет дат» проверял бы генератор случайных чисел.
_NATAL_PLANETS = [
    {"name": "Sun",        "longitude": 84.3,  "sign": "Gemini"},
    {"name": "Moon",       "longitude": 344.6, "sign": "Pisces"},
    {"name": "Mercury",    "longitude": 65.6,  "sign": "Gemini"},
    {"name": "Venus",      "longitude": 47.2,  "sign": "Taurus"},
    {"name": "Mars",       "longitude": 12.9,  "sign": "Aries"},
    {"name": "Jupiter",    "longitude": 106.8, "sign": "Cancer"},
    {"name": "Saturn",     "longitude": 291.4, "sign": "Capricorn"},
    {"name": "Uranus",     "longitude": 277.1, "sign": "Capricorn"},
    {"name": "Neptune",    "longitude": 283.5, "sign": "Capricorn"},
    {"name": "Pluto",      "longitude": 225.2, "sign": "Scorpio"},
]

# Ключи именно `number`/`degree` — `_extract_cusps` читает только их, на чужой
# форме молча отдаёт двенадцать нулей, и блок планера возвращает пустоту.
_HOUSES = [{"number": i + 1, "degree": (185.7 + i * 30) % 360, "sign": "—"} for i in range(12)]


@pytest.fixture
def chart(db, user_free):
    row = NatalChart(
        user_id=user_free.id,
        birth_date="1990-06-15",
        birth_time="12:00",
        birth_place="Moscow",
        latitude=55.75,
        longitude=37.62,
        timezone="Europe/Moscow",
        planets=_NATAL_PLANETS,
        houses=_HOUSES,
        aspects=[],
    )
    db.add(row)
    user_free.primary_chart_id = row.id
    db.commit()
    db.refresh(row)
    return row


# ─────────────────────────── Окно отправки ───────────────────────────
class TestSendWindow:
    """Обе границы, одна функция на планировщик и на выдачу."""

    def _at(self, hh, mm=0):
        return datetime(2026, 9, 10, hh, mm)

    def test_before_daily_time_is_closed(self):
        assert in_send_window(self._at(7, 59), "08:00", "22:00") is False

    def test_exactly_daily_time_is_open(self):
        assert in_send_window(self._at(8, 0), "08:00", "22:00") is True

    def test_midday_is_open(self):
        assert in_send_window(self._at(14, 30), "08:00", "22:00") is True

    def test_after_quiet_from_is_closed(self):
        """Главная регрессия. До 10.09.2026 верхней границы не было вовсе, и
        тик в 23:45 проходил проверку — человека будили ночью."""
        assert in_send_window(self._at(23, 45), "08:00", "22:00") is False

    def test_exactly_quiet_from_is_closed(self):
        assert in_send_window(self._at(22, 0), "08:00", "22:00") is False

    def test_broken_pair_keeps_notifications_alive(self):
        """Верх не позже низа — верхняя граница игнорируется, а не гасит всё.

        Пустое окно означало бы, что кривая настройка молча выключает
        уведомления, и снаружи это неотличимо от сломанного планировщика.
        """
        assert in_send_window(self._at(23, 45), "08:00", "06:00") is True

    def test_garbage_falls_back_to_defaults(self):
        assert in_send_window(self._at(7, 0), "не время", None) is False
        assert in_send_window(self._at(12, 0), "не время", None) is True


class TestSchedulerUsesTheSameWindow:
    """Планировщик веб-пушей чинится тем же правилом — второй копии нет."""

    def test_night_tick_sends_nothing(self, db, user_free, chart, monkeypatch):
        sent = []
        monkeypatch.setattr(
            "backend.push.cron.send_to_user",
            lambda db_, uid, payload: sent.append(payload) or 1,
        )

        tz = pytz.timezone("Europe/Moscow")
        night = tz.localize(datetime(2026, 9, 10, 23, 45))

        class _FrozenDatetime(datetime):
            @classmethod
            def now(cls, tz_=None):
                return night.astimezone(tz_) if tz_ else night

        monkeypatch.setattr("backend.push.cron.datetime", _FrozenDatetime)

        assert _process_user(db, user_free) == 0
        assert sent == [], "ночной тик не должен ничего отправлять"


# ─────────────────── Дата границы транзита в тексте ───────────────────
# Правило: в тексте уведомления не должно быть НИ ОДНОЙ даты — только
# порядок величины («сегодня», «завтра», «через неделю»). Причина в CLAUDE.md,
# раздел «Отложено: лента не отдаёт границ транзита»: настоящих границ у
# события нет, и любая напечатанная дата будет выдуманной точностью.
#
# ⚠️ У пушей данные для нарушения ЕСТЬ — они зовут `calculate_transits`
# напрямую и держат `e.start_date` в руках (по нему же и отбирают события).
# То есть правило здесь держалось на том, что дату просто не подставляли в
# шаблон, и ничем не было закреплено. Этот класс и есть закрепление.
_DATE_PATTERNS = [
    re.compile(r"\d{4}-\d{2}-\d{2}"),                    # 2026-09-12
    re.compile(r"\b\d{1,2}[./]\d{1,2}([./]\d{2,4})?\b"),  # 12.09 / 12.09.2026
    re.compile(
        r"\b\d{1,2}\s+(янв|фев|март|апрел|ма[йя]|июн|июл|авг|сент|октя|ноя|дека)",
        re.IGNORECASE,
    ),                                                    # 12 сентября
]

_HUMAN_FIELDS = ("title", "body")


def _assert_no_dates(text: str, where: str):
    for pattern in _DATE_PATTERNS:
        found = pattern.search(text)
        assert not found, (
            f"{where}: в текст уведомления попала дата «{found.group(0)}» — "
            f"полный текст: {text!r}. Границ транзита у события нет, "
            f"напечатанная дата будет выдуманной точностью (CLAUDE.md)."
        )


class TestNoDatesInNotificationText:
    def test_candidates_never_print_a_date(self, db, user_free, chart):
        """Прямо по `_collect_candidates` — источник текста для обоих путей."""
        seen_kinds = set()
        start = date(2026, 9, 10)
        for offset in range(10):
            for cand in _collect_candidates(db, user_free, chart, start + timedelta(days=offset)):
                seen_kinds.add(cand["kind"])
                for field in _HUMAN_FIELDS:
                    _assert_no_dates(cand[field], f"{cand['kind']}.{field}")

        # Тест обязан что-то проверить: пустой список кандидатов прошёл бы
        # молча и годами держал место настоящей проверки.
        assert seen_kinds, "за 10 дней не нашлось ни одного кандидата — проверять нечего"

        # ⚠️ И отдельно — что проверен именно транзитный текст, а не только
        # «прогноз на день». Каждый блок `_collect_candidates` завёрнут в свой
        # `try/except` с `logger.warning`, то есть сломанный блок не роняет
        # сбор, а молча выпадает из выдачи. Проверено исполнением 10.09.2026:
        # карта без ключа `sign` у натальных планет даёт `transit candidates
        # failed: 'sign'` в лог и НОЛЬ транзитных кандидатов — при этом сам
        # запрет на даты остаётся зелёным, потому что проверять стало нечего.
        # Это ровно тот способ, которым замок разряжается незаметно.
        assert "transit" in seen_kinds, (
            "среди кандидатов нет ни одного транзита — блок транзитов выпал "
            "молча (см. logger.warning 'transit candidates failed'), и запрет "
            "на даты проверяет только текст прогноза дня"
        )

    def test_upcoming_payload_never_prints_a_date(self, db, user_free, chart):
        """То же по ответу ручки — там текст доезжает до человека."""
        result = collect_upcoming(db, user_free, days=7)
        assert result["events"], "пустая выдача — проверять нечего"
        for event in result["events"]:
            for field in _HUMAN_FIELDS:
                _assert_no_dates(event[field], f"{event['kind']}.{field}")

    def test_key_is_allowed_to_contain_a_date(self, db, user_free, chart):
        """Запрет — только на текст для человека. `key` собран из даты
        СОБЫТИЯ намеренно: он служебный, клиент его не показывает, и именно
        дата события делает его устойчивым между запросами."""
        result = collect_upcoming(db, user_free, days=7)
        assert any(re.search(r"\d{4}-\d{2}-\d{2}", e["key"]) for e in result["events"])


# ─────────────────────────── Сама выдача ───────────────────────────
class TestUpcoming:
    def test_events_are_in_the_future(self, db, user_free, chart):
        result = collect_upcoming(db, user_free, days=7)
        now = datetime.now(pytz.timezone(result["timezone"]))
        for event in result["events"]:
            assert datetime.fromisoformat(event["at"]) > now

    def test_events_are_inside_the_window(self, db, user_free, chart):
        user_free.push_daily_time = "09:00"
        user_free.push_quiet_from = "21:00"
        db.commit()
        result = collect_upcoming(db, user_free, days=5)
        for event in result["events"]:
            at = datetime.fromisoformat(event["at"])
            assert (at.hour, at.minute) == (9, 0)
            assert in_send_window(at, "09:00", "21:00")

    def test_keys_are_stable_between_calls(self, db, user_free, chart):
        """Ключ собран из события, а не из запроса: повтор даёт то же самое.
        Иначе клиент показал бы одно и то же событие дважды."""
        first = {e["key"] for e in collect_upcoming(db, user_free, days=5)["events"]}
        second = {e["key"] for e in collect_upcoming(db, user_free, days=5)["events"]}
        assert first == second

    def test_keys_are_unique(self, db, user_free, chart):
        events = collect_upcoming(db, user_free, days=7)["events"]
        keys = [e["key"] for e in events]
        assert len(keys) == len(set(keys))

    def test_key_matches_server_dedup_pair(self, db, user_free, chart):
        """`key` это `kind:ref_key` — та же пара, по которой сервер
        дедуплицирует отправленное (push_sent_log)."""
        for event in collect_upcoming(db, user_free, days=5)["events"]:
            assert event["key"].startswith(event["kind"] + ":")

    def test_no_primary_chart_gives_empty_list(self, db, user_free):
        result = collect_upcoming(db, user_free, days=7)
        assert result["events"] == []

    def test_disabled_toggles_are_respected(self, db, user_free, chart):
        """Отбор не продублирован: выключенные категории отваливаются тем же
        кодом, что и у веб-пушей."""
        user_free.push_daily_forecast = False
        user_free.push_planner = False
        user_free.push_key_transits = False
        user_free.push_moon_phases = False
        db.commit()
        assert collect_upcoming(db, user_free, days=7)["events"] == []

    def test_days_is_clamped(self, db, user_free, chart):
        assert collect_upcoming(db, user_free, days=999)["days"] == UPCOMING_MAX_DAYS
        assert collect_upcoming(db, user_free, days=0)["days"] == 1


class TestUpcomingHttp:
    def test_requires_auth(self, client):
        assert client.get("/api/v1/push/upcoming").status_code in (401, 403)

    def test_returns_events(self, client, auth_headers_free, chart):
        resp = client.get("/api/v1/push/upcoming?days=3", headers=auth_headers_free)
        assert resp.status_code == 200
        body = resp.json()
        assert body["days"] == 3
        assert body["timezone"] == "Europe/Moscow"
        for event in body["events"]:
            assert set(event) == {"key", "kind", "at", "title", "body", "url"}

    def test_rejects_days_out_of_range(self, client, auth_headers_free, chart):
        assert client.get("/api/v1/push/upcoming?days=0", headers=auth_headers_free).status_code == 422
        assert client.get(
            f"/api/v1/push/upcoming?days={UPCOMING_MAX_DAYS + 1}", headers=auth_headers_free
        ).status_code == 422

    def test_free_tier_is_not_gated(self, client, auth_headers_free, chart):
        """Гейта по тарифу нет ни здесь, ни в веб-пушах — решение владельца."""
        assert client.get("/api/v1/push/upcoming", headers=auth_headers_free).status_code == 200


class TestQuietFromSetting:
    def test_settings_expose_the_pair(self, client, auth_headers_free):
        body = client.get("/api/v1/push/settings", headers=auth_headers_free).json()
        assert body["daily_time"] == "08:00"
        assert body["quiet_from"] == "22:00"

    def test_patch_updates_quiet_from(self, client, auth_headers_free):
        resp = client.patch(
            "/api/v1/push/settings", json={"quiet_from": "21:30"}, headers=auth_headers_free
        )
        assert resp.status_code == 200
        assert resp.json()["quiet_from"] == "21:30"

    def test_patch_rejects_garbage(self, client, auth_headers_free):
        resp = client.patch(
            "/api/v1/push/settings", json={"quiet_from": "25:00"}, headers=auth_headers_free
        )
        assert resp.status_code == 422

    def test_patch_rejects_inverted_pair(self, client, auth_headers_free):
        """Пара проверяется целиком: прислать можно одну границу, а
        осмысленность у них только совместная."""
        resp = client.patch(
            "/api/v1/push/settings", json={"quiet_from": "06:00"}, headers=auth_headers_free
        )
        assert resp.status_code == 422
