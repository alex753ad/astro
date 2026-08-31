"""POST /api/v1/charts/{id}/share — не выдавать новый токен на живую ссылку.

До правки ручка держала один и тот же public_token сколько угодно долго, но
БЕЗУСЛОВНО продлевала public_token_expires_at при каждом вызове — повторное
«Поделиться» откладывало срок жизни ссылки на очередные 90 дней, то есть
ссылка оставалась живой бессрочно, пока по ней хоть изредка делятся заново.
Решение владельца 31.08.2026: живой токен возвращать как есть, без
продления; новый выдавать только когда токена нет вообще или прежний уже
истёк.
"""

from datetime import timedelta

from backend.tests.test_chart_access import _make_chart
from backend.time_utils import utcnow


def test_second_call_returns_same_token(client, db, user_free, auth_headers_free):
    chart = _make_chart(db, user_id=user_free.id)

    resp1 = client.post(f"/api/v1/charts/{chart.id}/share", headers=auth_headers_free)
    assert resp1.status_code == 200, resp1.text
    token1 = resp1.json()["token"]

    resp2 = client.post(f"/api/v1/charts/{chart.id}/share", headers=auth_headers_free)
    assert resp2.status_code == 200, resp2.text
    token2 = resp2.json()["token"]

    assert token1 == token2


def test_second_call_does_not_extend_expiry(client, db, user_free, auth_headers_free):
    chart = _make_chart(db, user_id=user_free.id)

    resp1 = client.post(f"/api/v1/charts/{chart.id}/share", headers=auth_headers_free)
    assert resp1.status_code == 200, resp1.text
    db.refresh(chart)
    expires_at_1 = chart.public_token_expires_at

    resp2 = client.post(f"/api/v1/charts/{chart.id}/share", headers=auth_headers_free)
    assert resp2.status_code == 200, resp2.text
    db.refresh(chart)
    expires_at_2 = chart.public_token_expires_at

    assert expires_at_1 == expires_at_2


def test_expired_token_is_replaced_with_new_one(client, db, user_free, auth_headers_free):
    chart = _make_chart(db, user_id=user_free.id)

    resp1 = client.post(f"/api/v1/charts/{chart.id}/share", headers=auth_headers_free)
    assert resp1.status_code == 200, resp1.text
    token1 = resp1.json()["token"]

    # Форсируем истёкший срок, как будто прошло 91 день.
    db.refresh(chart)
    chart.public_token_expires_at = utcnow() - timedelta(days=1)
    db.commit()

    resp2 = client.post(f"/api/v1/charts/{chart.id}/share", headers=auth_headers_free)
    assert resp2.status_code == 200, resp2.text
    token2 = resp2.json()["token"]

    assert token1 != token2
    db.refresh(chart)
    assert chart.public_token_expires_at > utcnow()
