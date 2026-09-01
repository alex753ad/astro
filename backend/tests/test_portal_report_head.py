"""HEAD /portal-report/{token} — публичный PDF по токену.

Ссылку на этот PDF присылают в мессенджер, а краулер превью проверяет
ресурс HEAD-запросом до GET. FastAPI, в отличие от Starlette, не добавляет
HEAD к GET-маршрутам сам (fastapi/routing.py:892 против
starlette/routing.py:229-234), поэтому ручка отвечала 405 — как и обе ручки
шаринга, см. TestHeadRequests в test_share_page.py.

Отдельный файл, а не дописка к CRM-тестам: здесь проверяется свойство
ручки как публичной точки входа, а не логика портала.
"""

from datetime import date, timedelta

import pytest

from backend.models import (
    AstrologerProfile,
    ClientPortalAccess,
    ClientProfile,
    NatalChart,
    User,
)
from backend.auth.passwords import hash_password
from backend.time_utils import utcnow


@pytest.fixture
def portal_token(db):
    """Живой портал с рассчитанной картой. Возвращает токен."""
    user = User(
        email="astrolog@example.com",
        hashed_password=hash_password("Password123!"),
        name="Астролог",
        tier="premium",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    astrologer = AstrologerProfile(user_id=user.id, display_name="Астролог Ольга")
    db.add(astrologer)
    db.commit()
    db.refresh(astrologer)

    chart = NatalChart(
        user_id=user.id,
        birth_date="1990-06-15",
        birth_time="10:30",
        birth_place="Moscow",
        latitude=55.75,
        longitude=37.62,
        timezone="Europe/Moscow",
        planets=[{"name": "Sun", "longitude": 84.5, "sign": "Gemini",
                  "degree_in_sign": 24.5, "house": 10, "retrograde": False}],
        houses=[{"number": i + 1, "sign": "Aries", "degree": float(i * 30)} for i in range(12)],
        aspects=[],
        ascendant={"sign": "Leo", "degree": 5.0, "longitude": 125.0},
    )
    db.add(chart)
    db.commit()
    db.refresh(chart)

    client_profile = ClientProfile(
        astrologer_id=astrologer.id,
        name="Мария Иванова",
        birth_date=date(1990, 6, 15),
        birth_place="Moscow",
        natal_chart_id=chart.id,
    )
    db.add(client_profile)
    db.commit()
    db.refresh(client_profile)

    access = ClientPortalAccess(
        client_id=client_profile.id,
        token="portal-token-test",
        enabled=True,
        expires_at=utcnow() + timedelta(days=30),
    )
    db.add(access)
    db.commit()
    return access.token


def test_head_returns_200_pdf(client, portal_token):
    resp = client.head(f"/portal-report/{portal_token}")

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content == b""


def test_head_does_not_generate_pdf(client, portal_token, monkeypatch):
    """Ранний выход стоит до generate_pdf_bytes — ReportLab собирает PDF
    целиком и синхронно, а тело всё равно отбрасывается на уровне ASGI.
    """
    import backend.natal_pdf

    def _boom(*a, **kw):
        raise AssertionError("генерация PDF при HEAD не должна вызываться")

    monkeypatch.setattr(backend.natal_pdf, "generate_pdf_bytes", _boom)

    assert client.head(f"/portal-report/{portal_token}").status_code == 200


def test_head_on_bad_token_leaks_no_personal_data(client, db):
    """Content-Disposition содержит имя клиента и дату рождения.

    Если он начнёт считаться до проверок 404 (например при «упрощении»
    порядка строк), HEAD с чужим или протухшим токеном начнёт отдавать
    персональные данные, не отдав ни байта PDF. Тест закрепляет порядок.
    """
    resp = client.head("/portal-report/does-not-exist")

    assert resp.status_code == 404
    assert "content-disposition" not in {k.lower() for k in resp.headers}


def test_head_matches_get_on_bad_token(client, db):
    """Иначе ручка станет оракулом существования порталов."""
    get_code = client.get("/portal-report/does-not-exist").status_code
    head_code = client.head("/portal-report/does-not-exist").status_code

    assert head_code == get_code == 404
