"""Анонимные карты в /api/v1/admin/stats — верх воронки.

Анонимная карта = NatalChart.user_id IS NULL (models.py:108). Считается по
существующим полям и по всей истории: удаления natal_charts в бэкенде нет
нигде, expires_at (models.py:138) только закрывает доступ в
resolve_chart_access, саму запись не трогает.

Конверсия «аноним → регистрация» здесь НЕ проверяется, потому что не
считается в принципе: /chart/save-anonymous пересчитывает карту заново и
вставляет новую строку, анонимную не привязывая и никак не помечая — связи
между записями не существует. Подробно в CLAUDE.md.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from backend.auth.jwt import create_access_token
from backend.auth.passwords import hash_password
from backend.models import NatalChart, User
from backend.time_utils import utcnow

STATS_URL = "/api/v1/admin/stats"


@pytest.fixture
def admin_headers(db):
    admin = User(
        email="admin-anon@example.com",
        hashed_password=hash_password("Password123!"),
        name="Admin", tier="premium", is_admin=True,
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    return {"Authorization": f"Bearer {create_access_token(
        user_id=admin.id, email=admin.email, tier=admin.tier)}"}


def _user(db, email, tier="free"):
    u = User(email=email, hashed_password=hash_password("Password123!"),
             name=email, tier=tier)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


class TestAnonCharts:
    """Верх воронки: карты, построенные без регистрации (user_id IS NULL).
    Считаются по существующим полям — удаления natal_charts в бэкенде нет
    нигде, поэтому история полная."""

    def _chart(self, db, user_id, days_ago):
        db.add(NatalChart(
            user_id=user_id, birth_date="1990-01-10", birth_time="12:00",
            birth_place="Moscow", latitude=55.75, longitude=37.62,
            timezone="Europe/Moscow", planets=[], houses=[], aspects=[],
            created_at=utcnow() - timedelta(days=days_ago),
        ))

    def test_counts_by_period_and_share(self, client, db, admin_headers):
        u = _user(db, "owner@example.com", tier="free")
        self._chart(db, None, 1)      # аноним, попадает в 7д и 30д
        self._chart(db, None, 10)     # аноним, только в 30д
        self._chart(db, None, 100)    # аноним, только в total
        self._chart(db, u.id, 1)      # зарегистрированный — не аноним
        db.commit()

        resp = client.get(STATS_URL, headers=admin_headers)
        assert resp.status_code == 200, resp.text
        anon = resp.json()["anon_charts"]

        assert anon["total"] == 3
        assert anon["last_30d"] == 2
        assert anon["last_7d"] == 1
        # 3 анонимных из 4 карт всего
        assert anon["share_pct"] == 75

    def test_no_division_by_zero_on_empty_db(self, client, db, admin_headers):
        resp = client.get(STATS_URL, headers=admin_headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["anon_charts"] == {
            "total": 0, "last_30d": 0, "last_7d": 0, "share_pct": 0,
        }
