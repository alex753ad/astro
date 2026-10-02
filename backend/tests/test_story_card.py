"""Карточка дня для сторис (флаг story_card, backend/story_card.py) и
источник регистрации (users.signup_source, 074)."""
from __future__ import annotations

import json as _json
from datetime import date, datetime
from unittest.mock import AsyncMock, patch

import pytest
import pytz

from backend import day_event as de
from backend import flags
from backend import story_card as sc
from backend.models import FeatureFlag, NatalChart, StoryCardShare, User
from backend.tests.test_push_upcoming import chart  # noqa: F401 — фикстура

TZ = pytz.timezone("Europe/Moscow")


def _ev(transit="Moon", natal="Venus", aspect="trine"):
    return de.DayEvent(key="k", at_local=TZ.localize(datetime(2026, 10, 1, 15, 1)),
                       transit=transit, natal=natal, aspect=aspect, score=6, timed=True)


@pytest.fixture(autouse=True)
def _fresh_flags():
    flags.reset_cache()
    yield
    flags.reset_cache()


@pytest.fixture
def flag_on(db, user_free):
    db.add(FeatureFlag(key=sc.FLAG, mode="users", user_ids=[user_free.id]))
    db.commit()
    flags.reset_cache()


class TestPhrases:
    """Таблицы согласованы владельцем 01.10.2026 (docs/story_card_phrases.md)."""

    def _all(self):
        return ([p for row in sc.STORY_PHRASE.values() for p in row]
                + list(sc.LUNATION_PHRASE.values()) + [p for _, p in sc.PHASES.values()])

    def test_every_natal_point_of_main_event_has_phrases(self):
        assert set(sc.STORY_PHRASE) == set(de._YOURS_DAT)

    def test_counts(self):
        assert len(self._all()) == 12 * 3 + 2 + 8

    def test_short_and_unique(self):
        phrases = self._all()
        assert max(map(len, phrases)) <= 32
        assert len(phrases) == len(set(phrases))


class TestText:
    def test_moon_to_venus(self):
        ev = _ev()
        assert sc.event_label(ev) == "Луна × Венера"
        assert sc.phrase(ev, "waning_gibbous") == "Сегодня я радую себя"

    @pytest.mark.parametrize("planet,label", [
        ("Moon", "Луна × моя Луна"), ("Venus", "Венера × моя Венера"),
        ("Sun", "Солнце × моё Солнце"), ("Mars", "Марс × мой Марс"),
    ])
    def test_planet_to_itself(self, planet, label):
        assert sc.event_label(_ev(transit=planet, natal=planet)) == label

    def test_every_planet_has_my_form(self):
        assert set(sc._MY) == set(sc._FIGURE_PLANETS)

    def test_tone_picks_column(self):
        assert sc.phrase(_ev(aspect="square"), "new_moon") == "Я радуюсь без лишних трат"
        assert sc.phrase(_ev(aspect="conjunction"), "new_moon") == "Я окружаю себя красивым"

    @pytest.mark.parametrize("natal", ["Ascendant", "Midheaven"])
    def test_asc_mc_phrase_without_event(self, natal):
        ev = _ev(natal=natal)
        assert sc.event_label(ev) is None
        assert sc.phrase(ev, "new_moon") == sc.STORY_PHRASE[natal][0]

    def test_lunation(self):
        ev = _ev(transit="full_moon", natal=None, aspect=None)
        assert sc.event_label(ev) is None
        assert sc.phrase(ev, "waning_gibbous") == "Я завершаю начатое"

    def test_no_event_phrase_by_phase(self):
        assert sc.phrase(None, "waning_gibbous") == "Я делюсь теплом"


class TestMoonPhase:
    # Новолуние 10.10.2026 и полнолуние 26.09.2026 — по lunar_engine.
    @pytest.mark.parametrize("day,phase", [
        (date(2026, 10, 10), "new_moon"),
        (date(2026, 9, 26), "full_moon"),
        (date(2026, 10, 1), "waning_gibbous"),
        (date(2026, 10, 3), "last_quarter"),
    ])
    def test_known_days(self, day, phase):
        assert sc.moon_phase(day, "Europe/Moscow") == phase


class TestFigure:
    def test_shape(self, chart):
        fig = sc.figure(chart)
        n = len(fig["points"])
        assert n and fig["lines"]
        assert all(0 <= a < 360 for a in fig["points"])
        assert all(0 <= i < j < n for i, j in fig["lines"])
        assert {k for line in fig["lines"] for k in line} == set(range(n))

    def test_stable_for_chart(self, chart):
        assert sc.figure(chart) == sc.figure(chart)

    def test_not_tied_to_aries_or_ascendant(self, chart):
        # Солнце 84.3° — если бы поворота не было, вершина стояла бы на 84.3.
        assert 84.3 not in sc.figure(chart)["points"]

    def test_time_unknown_drops_moon(self, chart, db):
        with_moon = sc.figure(chart)
        chart.time_unknown = True
        without = sc.figure(chart)
        # У фикстуры Луна в аспектах есть — без неё вершин меньше.
        assert len(without["points"]) < len(with_moon["points"])


class TestCard:
    def test_lunation_day_names_phase(self, chart, user_free, monkeypatch):
        monkeypatch.setattr(de, "main_event", lambda *a, **k: _ev("new_moon", None, None))
        got = sc.card(user_free, chart, date(2026, 10, 1))
        assert got["phase"] == "новолуние"
        assert got["phrase"] == "Я выбираю, с чего начать"
        assert got["event"] is None

    def test_no_event(self, chart, user_free, monkeypatch):
        monkeypatch.setattr(de, "main_event", lambda *a, **k: None)
        got = sc.card(user_free, chart, date(2026, 10, 1))
        assert got == {**got, "date": "2026-10-01", "event": None,
                       "phase": "убывающая Луна", "phrase": "Я делюсь теплом"}


class TestEndpoints:
    def _today(self):
        return datetime.now(TZ).date().isoformat()

    def test_flag_off_404(self, client, auth_headers_free, chart):
        assert client.get(f"/api/v1/chart/{chart.id}/story-card?date={self._today()}",
                          headers=auth_headers_free).status_code == 404
        assert client.post("/api/v1/story-card/shared", json={"variant": "chart"},
                           headers=auth_headers_free).status_code == 404

    def test_card(self, client, auth_headers_free, chart, flag_on):
        r = client.get(f"/api/v1/chart/{chart.id}/story-card?date={self._today()}",
                       headers=auth_headers_free)
        assert r.status_code == 200
        assert set(r.json()) == {"date", "phrase", "event", "phase", "figure"}

    def test_far_date_422(self, client, auth_headers_free, chart, flag_on):
        r = client.get(f"/api/v1/chart/{chart.id}/story-card?date=2026-01-01",
                       headers=auth_headers_free)
        assert r.status_code == 422

    def test_foreign_chart_404(self, client, auth_headers_free, flag_on, db):
        other = User(email="other@yandex.ru", tier="free")
        db.add(other)
        db.flush()
        foreign = NatalChart(user_id=other.id, birth_date="1990-01-01", birth_place="X",
                             latitude=0, longitude=0, timezone="UTC", planets=[], houses=[], aspects=[])
        db.add(foreign)
        db.commit()
        r = client.get(f"/api/v1/chart/{foreign.id}/story-card?date={self._today()}",
                       headers=auth_headers_free)
        assert r.status_code == 404

    def test_shared_counts(self, client, auth_headers_free, flag_on, db, user_free):
        assert client.post("/api/v1/story-card/shared", json={"variant": "photo"},
                           headers=auth_headers_free).status_code == 204
        assert client.post("/api/v1/story-card/shared", json={"variant": "x"},
                           headers=auth_headers_free).status_code == 422
        rows = db.query(StoryCardShare).filter_by(user_id=user_free.id).all()
        assert [r.variant for r in rows] == ["photo"]


class TestSignupSource:
    EMAIL = "story-src@yandex.ru"

    @pytest.fixture
    def no_mail(self):
        with patch("backend.email_service.send_otp_email", new_callable=AsyncMock), \
             patch("backend.email_service._send", new_callable=AsyncMock):
            yield

    async def _register(self, client, fake_redis, source):
        from backend.auth.router import _otp_key
        client.post("/api/v1/auth/register/email/send-code", json={
            "email": self.EMAIL, "password": "Password123!", "consent": True,
            "signup_source": source,
        })
        code = _json.loads(await fake_redis.get(_otp_key(self.EMAIL)))["code"]
        r = client.post("/api/v1/auth/register/email/verify", json={"email": self.EMAIL, "code": code})
        assert r.status_code == 201

    @pytest.mark.asyncio
    async def test_saved(self, client, fake_redis, no_mail, db):
        await self._register(client, fake_redis, "story/share/day_card")
        assert db.query(User).filter_by(email=self.EMAIL).one().signup_source == "story/share/day_card"

    @pytest.mark.asyncio
    async def test_garbage_does_not_break_registration(self, client, fake_redis, no_mail, db):
        await self._register(client, fake_redis, "<script>")
        assert db.query(User).filter_by(email=self.EMAIL).one().signup_source is None
