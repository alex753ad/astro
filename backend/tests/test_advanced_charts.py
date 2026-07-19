"""Соляр, синастрия, релокация: админ-гейт, расчёты и формат ответов."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from backend.auth.jwt import create_access_token
from backend.auth.passwords import hash_password
from backend.models import User


# ── Фикстуры ──────────────────────────────────────────────

@pytest.fixture
def admin_user(db):
    user = User(
        email="admin@yandex.ru",
        hashed_password=hash_password("Password123!"),
        name="Admin",
        tier="premium",
        is_admin=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def admin_headers(admin_user):
    token = create_access_token(
        user_id=admin_user.id, email=admin_user.email, tier=admin_user.tier
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_chart(db, admin_user):
    """Карта админа с натальным Солнцем и utc_datetime."""
    from backend.tests.test_chart_access import _make_chart

    chart = _make_chart(db, user_id=admin_user.id)
    chart.utc_datetime = datetime(1990, 6, 15, 7, 30)
    chart.planets = [{
        "name": "Sun", "longitude": 84.5, "sign": "Gemini",
        "degree_in_sign": 24.5, "house": 10, "retrograde": False,
    }]
    db.commit()
    db.refresh(chart)
    return chart


@pytest.fixture
def geo_mock():
    from backend.ephemeris.geo import GeoResult

    result = GeoResult(
        latitude=41.39, longitude=2.16,
        display_name="Barcelona, Spain", timezone="Europe/Madrid",
    )
    with patch("backend.advanced_charts_router.geocode_place",
               new_callable=AsyncMock, return_value=result) as m:
        yield m


PARTNER = {
    "name": "Партнёр",
    "birth_date": "1992-03-20",
    "birth_time": "14:00",
    "birth_place": "Barcelona",
    "house_system": "placidus",
}


# ═══════════════════════════════════════════════════════════
# ДОСТУП
# ═══════════════════════════════════════════════════════════

class TestAdminOnlyAccess:
    """Не-админ с валидным JWT получает 403 на всех шести эндпоинтах."""

    def test_solar_return_post(self, client, db, user_free, auth_headers_free):
        from backend.tests.test_chart_access import _make_chart
        chart = _make_chart(db, user_id=user_free.id)
        resp = client.post(
            f"/api/v1/chart/{chart.id}/solar-return",
            json={"year": 2026}, headers=auth_headers_free,
        )
        assert resp.status_code == 403

    def test_relocation_post(self, client, db, user_free, auth_headers_free):
        from backend.tests.test_chart_access import _make_chart
        chart = _make_chart(db, user_id=user_free.id)
        resp = client.post(
            f"/api/v1/chart/{chart.id}/relocation",
            json={"location": "Barcelona"}, headers=auth_headers_free,
        )
        assert resp.status_code == 403

    def test_synastry_post(self, client, db, user_free, auth_headers_free):
        from backend.tests.test_chart_access import _make_chart
        chart = _make_chart(db, user_id=user_free.id)
        resp = client.post(
            "/api/v1/chart/synastry",
            json={"chart_id": chart.id, "partner": PARTNER}, headers=auth_headers_free,
        )
        assert resp.status_code == 403

    def test_synastry_interpret(self, client, db, user_free, auth_headers_free):
        from backend.tests.test_chart_access import _make_chart
        chart = _make_chart(db, user_id=user_free.id)
        resp = client.post(
            "/api/v1/chart/synastry/interpret",
            json={"chart_id": chart.id, "partner": PARTNER}, headers=auth_headers_free,
        )
        assert resp.status_code == 403

    def test_solar_return_sse(self, client, db, user_free, auth_headers_free):
        from backend.tests.test_chart_access import _make_chart
        chart = _make_chart(db, user_id=user_free.id)
        resp = client.get(
            f"/api/v1/chart/{chart.id}/solar-return/2026/interpret",
            headers=auth_headers_free,
        )
        assert resp.status_code == 403

    def test_relocation_sse(self, client, db, user_free, auth_headers_free):
        from backend.tests.test_chart_access import _make_chart
        chart = _make_chart(db, user_id=user_free.id)
        resp = client.get(
            f"/api/v1/chart/{chart.id}/relocation/interpret?location=Barcelona",
            headers=auth_headers_free,
        )
        assert resp.status_code == 403

    def test_anonymous_rejected(self, client, admin_chart):
        resp = client.post(
            f"/api/v1/chart/{admin_chart.id}/solar-return", json={"year": 2026}
        )
        assert resp.status_code in (401, 403)

    def test_sse_ticket_of_non_admin_rejected(self, client, db, user_free,
                                              auth_headers_free, admin_chart):
        """Тикет выдаётся любому — роль проверяется на самом эндпоинте."""
        ticket = client.post(
            "/api/v1/auth/sse-ticket", headers=auth_headers_free
        ).json()["ticket"]
        resp = client.get(
            f"/api/v1/chart/{admin_chart.id}/relocation/interpret"
            f"?location=Barcelona&ticket={ticket}"
        )
        assert resp.status_code == 403


# ═══════════════════════════════════════════════════════════
# СОЛЯР
# ═══════════════════════════════════════════════════════════

class TestSolarReturn:

    @pytest.mark.integration
    def test_returns_chart_with_exact_moment(self, client, admin_chart, admin_headers):
        resp = client.post(
            f"/api/v1/chart/{admin_chart.id}/solar-return",
            json={"year": 2026}, headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["solar_return_datetime"].startswith("2026-")
        assert len(data["planets"]) > 0
        assert len(data["houses"]) == 12

    @pytest.mark.integration
    def test_moment_is_near_birthday(self, client, admin_chart, admin_headers):
        """Соляр приходится на дни рождения ±несколько суток, а не на середину года."""
        resp = client.post(
            f"/api/v1/chart/{admin_chart.id}/solar-return",
            json={"year": 2026}, headers=admin_headers,
        )
        moment = datetime.fromisoformat(resp.json()["solar_return_datetime"])
        assert moment.month == 6
        assert abs(moment.day - 15) <= 3

    def test_rejects_chart_without_sun(self, client, db, admin_user, admin_headers):
        from backend.tests.test_chart_access import _make_chart
        chart = _make_chart(db, user_id=admin_user.id)
        chart.planets = [{"name": "Moon", "longitude": 10.0, "sign": "Aries",
                          "degree_in_sign": 10.0, "house": 1, "retrograde": False}]
        chart.utc_datetime = datetime(1990, 6, 15, 7, 30)
        db.commit()

        resp = client.post(
            f"/api/v1/chart/{chart.id}/solar-return",
            json={"year": 2026}, headers=admin_headers,
        )
        assert resp.status_code == 422

    def test_year_out_of_range_rejected(self, client, admin_chart, admin_headers):
        resp = client.post(
            f"/api/v1/chart/{admin_chart.id}/solar-return",
            json={"year": 1800}, headers=admin_headers,
        )
        assert resp.status_code == 422

    def test_foreign_chart_is_404(self, client, db, user_free, admin_headers):
        """Админ-доступ не отменяет проверку владельца карты."""
        from backend.tests.test_chart_access import _make_chart
        chart = _make_chart(db, user_id=user_free.id)
        resp = client.post(
            f"/api/v1/chart/{chart.id}/solar-return",
            json={"year": 2026}, headers=admin_headers,
        )
        assert resp.status_code == 404


class TestSolarReturnPrecision:
    """Точность момента возврата — суть расчёта."""

    @pytest.mark.integration
    def test_sun_returns_to_natal_longitude(self):
        from backend.ephemeris.calculator import PLANETS, _calc_planet_position, _datetime_to_jd
        from backend.ephemeris.aspects import _angular_distance
        from backend.ephemeris.solar_return import find_solar_return

        natal_lon = 84.5
        moment = find_solar_return(natal_lon, datetime(1990, 6, 15, 7, 30), 2026)

        lon, _, _, _ = _calc_planet_position(PLANETS["Sun"], _datetime_to_jd(moment))
        # Меньше угловой минуты — на порядок точнее, чем расчёт «на полдень».
        assert _angular_distance(lon, natal_lon) < 1 / 60


# ═══════════════════════════════════════════════════════════
# СИНАСТРИЯ
# ═══════════════════════════════════════════════════════════

class TestSynastryAspects:
    """Межкарточная сетка: полная решётка, а не пары внутри одного списка."""

    def _planet(self, name, lon):
        from backend.ephemeris.calculator import PlanetResult
        return PlanetResult(
            name=name, longitude=lon, latitude=0.0, distance=1.0, speed=1.0,
            sign="Aries", degree_in_sign=0.0, retrograde=False,
        )

    def test_same_named_planets_are_compared(self):
        """Солнце одного к Солнцу другого — связь, которой нет в натальной сетке."""
        from backend.ephemeris.synastry import calculate_synastry_aspects

        aspects = calculate_synastry_aspects(
            [self._planet("Sun", 10.0)], [self._planet("Sun", 12.0)]
        )
        assert len(aspects) == 1
        assert aspects[0].aspect_type == "conjunction"

    def test_both_directions_present(self):
        """Венера А × Марс Б и Марс А × Венера Б — разные связи."""
        from backend.ephemeris.synastry import calculate_synastry_aspects

        aspects = calculate_synastry_aspects(
            [self._planet("Venus", 0.0), self._planet("Mars", 90.0)],
            [self._planet("Venus", 90.0), self._planet("Mars", 0.0)],
        )
        pairs = {(a.planet1, a.planet2) for a in aspects}
        assert ("Venus", "Mars") in pairs
        assert ("Mars", "Venus") in pairs

    def test_out_of_orb_excluded(self):
        from backend.ephemeris.synastry import calculate_synastry_aspects

        aspects = calculate_synastry_aspects(
            [self._planet("Mercury", 0.0)], [self._planet("Jupiter", 45.0)]
        )
        assert aspects == []

    def test_sorted_by_importance_then_orb(self):
        from backend.ephemeris.synastry import calculate_synastry_aspects

        aspects = calculate_synastry_aspects(
            [self._planet("Sun", 0.0), self._planet("Jupiter", 0.0)],
            [self._planet("Moon", 1.0), self._planet("Saturn", 3.0)],
        )
        importances = [a.importance for a in aspects]
        assert importances == sorted(importances, key=lambda i: {"high": 0, "medium": 1, "low": 2}[i])

    def test_applying_is_false(self):
        """Карты неподвижны друг относительно друга — сходимости нет."""
        from backend.ephemeris.synastry import calculate_synastry_aspects

        aspects = calculate_synastry_aspects(
            [self._planet("Sun", 0.0)], [self._planet("Moon", 2.0)]
        )
        assert all(a.applying is False for a in aspects)


class TestSynastryEndpoint:

    @pytest.mark.integration
    def test_returns_two_charts_and_cross_aspects(self, client, admin_chart,
                                                  admin_headers, geo_mock):
        resp = client.post(
            "/api/v1/chart/synastry",
            json={"chart_id": admin_chart.id, "partner": PARTNER},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "chart1" in data and "chart2" in data
        assert isinstance(data["cross_aspects"], list)

    def test_invalid_partner_date_rejected(self, client, admin_chart, admin_headers):
        bad = {**PARTNER, "birth_date": "20-03-1992"}
        resp = client.post(
            "/api/v1/chart/synastry",
            json={"chart_id": admin_chart.id, "partner": bad}, headers=admin_headers,
        )
        assert resp.status_code == 422


# ═══════════════════════════════════════════════════════════
# РЕЛОКАЦИЯ
# ═══════════════════════════════════════════════════════════

class TestRelocation:

    @pytest.mark.integration
    def test_returns_relocated_chart(self, client, admin_chart, admin_headers, geo_mock):
        resp = client.post(
            f"/api/v1/chart/{admin_chart.id}/relocation",
            json={"location": "Barcelona"}, headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["relocated_location"] == "Barcelona, Spain"
        assert data["latitude"] == pytest.approx(41.39)

    @pytest.mark.integration
    def test_birth_moment_unchanged(self, client, admin_chart, admin_headers, geo_mock):
        """Меняются координаты, а дата и время рождения — нет."""
        resp = client.post(
            f"/api/v1/chart/{admin_chart.id}/relocation",
            json={"location": "Barcelona"}, headers=admin_headers,
        )
        assert resp.json()["birth_date"] == admin_chart.birth_date

    def test_missing_location_rejected(self, client, admin_chart, admin_headers):
        resp = client.post(
            f"/api/v1/chart/{admin_chart.id}/relocation", json={}, headers=admin_headers
        )
        assert resp.status_code == 422

    def test_chart_without_utc_datetime_rejected(self, client, db, admin_user,
                                                 admin_headers, geo_mock):
        from backend.tests.test_chart_access import _make_chart
        chart = _make_chart(db, user_id=admin_user.id)
        chart.utc_datetime = None
        db.commit()

        resp = client.post(
            f"/api/v1/chart/{chart.id}/relocation",
            json={"location": "Barcelona"}, headers=admin_headers,
        )
        assert resp.status_code == 422


# ═══════════════════════════════════════════════════════════
# ПРОМПТЫ
# ═══════════════════════════════════════════════════════════

class TestPrompts:

    def _profile(self):
        return {
            "planets": [{"name": "Sun", "sign": "Gemini", "degree_in_sign": 24.5, "house": 10}],
            "houses": [{"number": 1, "sign": "Leo", "degree": 5.0}],
            "aspects": [],
            "ascendant": {"sign": "Leo", "degree": 5.0},
            "midheaven": {"sign": "Taurus", "degree": 10.0},
        }

    def test_solar_return_prompt_mentions_year_and_moment(self):
        from backend.interpretation.advanced_prompts import build_solar_return_prompt

        prompt = build_solar_return_prompt(
            self._profile(), self._profile(), 2026, "2026-06-15T07:30:00", "Москва"
        )
        assert "2026" in prompt
        assert "2026-06-15T07:30:00" in prompt
        assert "Москва" in prompt

    def test_synastry_prompt_includes_both_names(self):
        from backend.interpretation.advanced_prompts import build_synastry_prompt

        prompt = build_synastry_prompt(
            self._profile(), self._profile(), [], name1="Аня", name2="Борис"
        )
        assert "Аня" in prompt and "Борис" in prompt

    def test_relocation_prompt_warns_against_signs(self):
        """Промпт должен явно запрещать трактовать знаки — они не меняются."""
        from backend.interpretation.advanced_prompts import build_relocation_prompt

        prompt = build_relocation_prompt(self._profile(), self._profile(), "Барселона")
        assert "Барселона" in prompt
        assert "не изменились" in prompt


class TestValidatorAllowsNewContexts:
    """Валидатор ищет натальные ключевые слова — новые контексты их не содержат."""

    @pytest.mark.parametrize("context", ["solar_return", "synastry", "relocation"])
    def test_new_contexts_not_rejected(self, context):
        from backend.interpretation.router import get_router

        text = "Этот год принесёт смену обстановки. " * 10
        assert get_router()._validate_response(text, [], context) is True

    def test_natal_still_validated(self):
        from backend.interpretation.router import get_router

        text = "Полный текст без нужных слов. " * 10
        assert get_router()._validate_response(text, [], "natal") is False
