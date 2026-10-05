"""Разбор касания к ASC/MC — с фактами (аудит 8.1, 05.10.2026).

До правки ручка брала натальные точки из chart_points.planets, где углов
нет: compute_exact_facts не находил MC и отдавал пустые знак, градус и даты,
модель писала разбор без данных. Точки — day_event.points, как в ленте.
"""
import pytest

from backend.tests.test_chart_access import _make_chart
from backend.tests.test_transit_event_cache_quota import (  # noqa: F401 — фикстуры
    clear_transit_interp_cache, fake_router,
)

# MC вымышленной карты test_exact_touch.py (08.03.1991 03:40, Москва):
# Сатурн трин MC — касание 17.04.2027 19:43 UTC.
MC = {"sign": "Sagittarius", "degree": 18.9395, "longitude": 258.9395}


def test_saturn_trine_mc_has_facts(client, db, user_pro, auth_headers_pro, fake_router, monkeypatch):
    from backend.transit import prompts

    seen = {}
    real = prompts.build_transit_event_prompt

    def spy(transit_event, **kw):
        seen.update(transit_event)
        return real(transit_event=transit_event, **kw)

    monkeypatch.setattr(prompts, "build_transit_event_prompt", spy)
    chart = _make_chart(db, user_id=user_pro.id)
    chart.midheaven = MC
    db.commit()

    resp = client.post(
        f"/api/v1/chart/{chart.id}/transits/event/interpret",
        json={"transit_planet": "Saturn", "natal_planet": "Midheaven",
              "aspect_type": "trine", "peak_date": "2027-04-17"},
        headers=auth_headers_pro,
    )
    assert resp.status_code == 200
    assert seen["natal_sign"] == "Sagittarius"
    assert seen["natal_degree"] == pytest.approx(18.94, abs=0.01)
    assert seen["transit_sign"] == "Aries"
    assert seen["exact_date"] == "2027-04-17"
    assert seen["period_start"] == "2027-04-06"
    assert seen["period_end"] == "2027-04-29"
