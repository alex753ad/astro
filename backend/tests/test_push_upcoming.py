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
    _transit_entry_candidates,
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
        # Окно выбрано так, чтобы в него попал ВХОД транзита в орб
        # (Юпитер в секстиле к Солнцу, 21.10.2026 на этой карте). После
        # правки отбора 10.09.2026 транзит перестал попадать в выдачу каждый
        # день — теперь это редкое событие, восемь раз за двести дней, — и
        # произвольное окно транзитного текста уже не содержит.
        start = date(2026, 10, 18)
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
        # Вечернее «прогноз на завтра» (с 24.09.2026) живёт своим временем:
        # при тихих часах с 21:00 оно переносится на 19:00 (evening_send_time).
        morning = [e for e in result["events"] if e["kind"] != "tomorrow"]
        evening = [e for e in result["events"] if e["kind"] == "tomorrow"]
        assert morning and evening, "в выборке нет одного из видов — проверка пустая"
        for event in morning:
            at = datetime.fromisoformat(event["at"])
            assert (at.hour, at.minute) == (9, 0)
            assert in_send_window(at, "09:00", "21:00")
        for event in evening:
            at = datetime.fromisoformat(event["at"])
            assert (at.hour, at.minute) == (19, 0)
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


class TestTransitEntry:
    """Транзит попадает в уведомления один раз — в день входа в орб."""

    def _entries(self, chart, start, days):
        """Длинные окна — прямо по функции отбора: она стоит 8 обращений к
        эфемеридам на день, тогда как полный `_collect_candidates` считает
        ещё планер, луну и две ретро-фазы."""
        out = []
        for offset in range(days):
            day = start + timedelta(days=offset)
            for cand in _transit_entry_candidates(chart, day, "/planner/x"):
                planet, natal, aspect, _d = cand["ref"].split(":")
                out.append(((planet, natal, aspect), day))
        return out

    def _entries_via_collect(self, db, user, chart, start, days):
        """Короткие окна — через реальный путь, чтобы проверялась и проводка
        функции в `_collect_candidates`, а не только она сама."""
        out = []
        for offset in range(days):
            day = start + timedelta(days=offset)
            for cand in _collect_candidates(db, user, chart, day):
                if cand["kind"] == "transit":
                    planet, natal, aspect, _d = cand["ref"].split(":")
                    out.append(((planet, natal, aspect), day))
        return out

    def test_ongoing_transit_does_not_repeat_next_day(self, chart):
        """⚠️ Регрессия на настоящий дефект, найденный 10.09.2026 глазами по
        выдаче ручки.

        `calculate_transits` ОБРЕЗАЕТ `start_date` окном запроса (проверено
        исполнением: Сатурн в квадрате к Нептуну отдаёт `start=2026-09-11` в
        окне того дня и `start=2026-09-12` в окне следующего — один и тот же
        транзит). Отбор же был устроен как `e.start_date == today`, поэтому
        под «начался сегодня» попадал ЛЮБОЙ идущий транзит, дата внутри ключа
        дедупа менялась каждый день, `push_sent_log` его не гасил — и человек
        получал одно и то же уведомление каждое утро неделями.

        Дефект был в веб-пушах; ручка лишь воспроизводила его точно.

        Порог 7 дней, а не «не в соседний день»: повторный вход после
        ретроградной петли законен, но случается через месяцы — на этой карте
        Юпитер в секстиле к Солнцу входит 21.10.2026 и снова 10.01.2027,
        через 81 день. Идущий транзит при дефекте давал попадание КАЖДЫЙ день.
        """
        hits = self._entries(chart, date(2026, 9, 10), 200)
        assert hits, "за 200 дней нет ни одного входа в орб — проверять нечего"

        by_triple: dict[tuple, list] = {}
        for triple, day in hits:
            by_triple.setdefault(triple, []).append(day)
        for triple, days in by_triple.items():
            days.sort()
            for prev, nxt in zip(days, days[1:]):
                assert (nxt - prev).days > 7, (
                    f"транзит {triple} попал в уведомления дважды за неделю: "
                    f"{prev} и {nxt} — это обрезка start_date окном запроса, "
                    f"а не два разных события"
                )

    def test_retrograde_reentry_is_allowed(self, chart):
        """Повторный вход после ретроградной петли — не дефект, а событие.
        Проверяется, чтобы будущая «починка» не задавила его дедупом."""
        hits = self._entries(chart, date(2026, 9, 10), 200)
        by_triple: dict[tuple, list] = {}
        for triple, day in hits:
            by_triple.setdefault(triple, []).append(day)
        repeated = {k: v for k, v in by_triple.items() if len(v) > 1}
        assert repeated, "на этой карте ожидался хотя бы один повторный вход"

    def test_entries_are_rare_on_the_real_path(self, db, user_free, chart):
        """Прямая мера дефекта через `_collect_candidates`: до правки транзит
        попадал в выдачу КАЖДЫЙ день, то есть здесь было бы ~30 попаданий."""
        hits = self._entries_via_collect(db, user_free, chart, date(2026, 10, 18), 30)
        assert len(hits) <= 5, (
            f"за 30 дней {len(hits)} транзитных уведомлений — похоже, снова "
            f"срабатывает на каждый идущий транзит, а не на вход в орб"
        )

    def test_entry_day_is_the_real_one(self, db, user_free, chart):
        """Ключ дедупа содержит настоящую дату входа в орб, а не дату
        запроса: именно на этом держится обещание про устойчивость `key`."""
        hits = self._entries_via_collect(db, user_free, chart, date(2026, 10, 18), 10)
        assert [d.isoformat() for _t, d in hits] == ["2026-10-21"]


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
            # target — куда вести в приложении (у daily — "feed_today"), у
            # остальных видов None; url остаётся для веба.
            assert set(event) == {"key", "kind", "at", "title", "body", "url", "target"}
            if event["kind"] == "daily":
                assert event["target"] == "feed_today"

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
