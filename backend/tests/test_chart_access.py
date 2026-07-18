"""Регрессия на IDOR: доступ к натальным картам.

Модель доступа:
  - карта с user_id — только владельцу;
  - анонимная карта (user_id IS NULL) — по X-Chart-Token;
  - во всех остальных случаях 404 (не 403), чтобы не раскрывать существование
    чужой карты.
"""

import secrets
from datetime import datetime, timedelta

import pytest

from backend.models import NatalChart


def _make_chart(db, user_id=None, access_token=None, expires_at=None):
    """Создаёт карту напрямую в БД, минуя эндпоинты."""
    chart = NatalChart(
        user_id=user_id,
        birth_date="1990-06-15",
        birth_time="10:30",
        birth_place="Moscow, Russia",
        latitude=55.75,
        longitude=37.62,
        timezone="Europe/Moscow",
        time_unknown=False,
        house_system="placidus",
        planets=[{
            "name": "Sun", "longitude": 84.5, "sign": "Gemini",
            "degree_in_sign": 24.5, "house": 10, "retrograde": False,
        }],
        houses=[{"number": i + 1, "sign": "Aries", "degree": float(i * 30)} for i in range(12)],
        aspects=[],
        ascendant={"sign": "Leo", "degree": 5.0, "longitude": 125.0},
        midheaven={"sign": "Taurus", "degree": 10.0, "longitude": 40.0},
        access_token=access_token,
        expires_at=expires_at,
    )
    db.add(chart)
    db.commit()
    db.refresh(chart)
    return chart


# ── Карты, принадлежащие пользователю ──────────────────────

class TestOwnedChartAccess:

    def test_owner_gets_200(self, client, db, user_free, auth_headers_free):
        chart = _make_chart(db, user_id=user_free.id)
        resp = client.get(f"/api/v1/chart/{chart.id}", headers=auth_headers_free)
        assert resp.status_code == 200
        assert resp.json()["id"] == chart.id

    def test_other_user_gets_404(self, client, db, user_free, auth_headers_pro):
        """Чужая карта не видна другому авторизованному пользователю."""
        chart = _make_chart(db, user_id=user_free.id)
        resp = client.get(f"/api/v1/chart/{chart.id}", headers=auth_headers_pro)
        assert resp.status_code == 404

    def test_anonymous_caller_gets_404(self, client, db, user_free):
        """Без авторизации чужая карта недоступна — это и был IDOR."""
        chart = _make_chart(db, user_id=user_free.id)
        resp = client.get(f"/api/v1/chart/{chart.id}")
        assert resp.status_code == 404

    def test_chart_token_does_not_bypass_ownership(self, client, db, user_free):
        """Capability-токен не даёт доступа к карте, у которой есть владелец."""
        token = secrets.token_urlsafe(32)
        chart = _make_chart(db, user_id=user_free.id, access_token=token)
        resp = client.get(f"/api/v1/chart/{chart.id}", headers={"X-Chart-Token": token})
        assert resp.status_code == 404


# ── Анонимные карты (legacy-строки с user_id IS NULL) ──────

class TestAnonymousChartAccess:

    def test_valid_token_gets_200(self, client, db):
        token = secrets.token_urlsafe(32)
        chart = _make_chart(db, access_token=token)
        resp = client.get(f"/api/v1/chart/{chart.id}", headers={"X-Chart-Token": token})
        assert resp.status_code == 200
        assert resp.json()["id"] == chart.id

    def test_no_token_gets_404(self, client, db):
        chart = _make_chart(db, access_token=secrets.token_urlsafe(32))
        resp = client.get(f"/api/v1/chart/{chart.id}")
        assert resp.status_code == 404

    def test_wrong_token_gets_404(self, client, db):
        chart = _make_chart(db, access_token=secrets.token_urlsafe(32))
        resp = client.get(
            f"/api/v1/chart/{chart.id}",
            headers={"X-Chart-Token": secrets.token_urlsafe(32)},
        )
        assert resp.status_code == 404

    def test_expired_token_gets_404(self, client, db):
        token = secrets.token_urlsafe(32)
        chart = _make_chart(
            db, access_token=token, expires_at=datetime.utcnow() - timedelta(days=1)
        )
        resp = client.get(f"/api/v1/chart/{chart.id}", headers={"X-Chart-Token": token})
        assert resp.status_code == 404

    def test_unexpired_token_gets_200(self, client, db):
        token = secrets.token_urlsafe(32)
        chart = _make_chart(
            db, access_token=token, expires_at=datetime.utcnow() + timedelta(days=1)
        )
        resp = client.get(f"/api/v1/chart/{chart.id}", headers={"X-Chart-Token": token})
        assert resp.status_code == 200

    def test_null_expiry_never_expires(self, client, db):
        """Legacy-карты без срока остаются доступными по токену."""
        token = secrets.token_urlsafe(32)
        chart = _make_chart(db, access_token=token, expires_at=None)
        resp = client.get(f"/api/v1/chart/{chart.id}", headers={"X-Chart-Token": token})
        assert resp.status_code == 200


# ── Защита распространяется на все chart-эндпоинты ─────────

class TestAllChartEndpointsProtected:

    @pytest.mark.parametrize("path,params", [
        ("", {}),
        ("/transits", {"from_date": "2025-01-01", "to_date": "2025-01-31"}),
        ("/transits/positions", {"on_date": "2025-01-01"}),
        ("/debug/cusps", {}),
    ])
    def test_foreign_chart_is_404(self, client, db, user_free, auth_headers_pro, path, params):
        chart = _make_chart(db, user_id=user_free.id)
        resp = client.get(f"/api/v1/chart/{chart.id}{path}", params=params,
                          headers=auth_headers_pro)
        assert resp.status_code == 404
