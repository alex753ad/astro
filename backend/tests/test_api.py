"""Integration tests for API endpoints."""

import pytest


class TestHealthEndpoints:
    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["version"] == "0.1.0"

    def test_health_db(self, client):
        resp = client.get("/health/db")
        assert resp.status_code == 200


class TestChartEndpoints:
    """Tests for natal chart calculation endpoint.

    Тесты, которым нужен живой Nominatim, помечены маркером `external` и в
    обычный прогон не попадают (см. addopts в pytest.ini). Запуск отдельно:
    `pytest backend/tests/ -m external`. Раньше они стояли под
    `skipif(True)`/`pytest.skip()` — то есть не запускались НИКОГДА и ни в
    одном отчёте не значились как отложенные намеренно.
    """

    @pytest.mark.external
    def test_calculate_chart(self, client):
        resp = client.post("/api/v1/chart/calculate", json={
            "birth_date": "2000-01-15",
            "birth_time": "14:30",
            "birth_place": "Berlin, Germany",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "id" in data
        assert len(data["planets"]) == 11
        assert len(data["houses"]) == 12
        assert data["time_unknown"] is False

    def test_calculate_chart_invalid_date(self, client):
        resp = client.post("/api/v1/chart/calculate", json={
            "birth_date": "1800-01-15",
            "birth_time": "14:30",
            "birth_place": "Berlin",
        })
        assert resp.status_code == 422

    @pytest.mark.external
    def test_calculate_chart_no_time(self, client):
        """Chart without birth time should use 12:00 noon."""
        resp = client.post("/api/v1/chart/calculate", json={
            "birth_date": "2000-01-15",
            "birth_place": "Berlin, Germany",
        })
        assert resp.status_code == 200
        assert resp.json()["time_unknown"] is True

    def test_get_nonexistent_chart(self, client):
        resp = client.get("/api/v1/chart/nonexistent-id")
        assert resp.status_code == 404
