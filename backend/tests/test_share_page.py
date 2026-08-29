"""GET /share/{token} — публичная страница шаринга с OG-тегами.

Аварийный путь (токен не найден / истёк) раньше отдавал голый JSON
исключения ({"detail": "..."}) вместо HTML — человек, перешедший по ссылке
из мессенджера, видел текст ошибки. Тесты проверяют оба пути: живой токен
даёт 200 с og:title, содержащим имя карты; истёкший — 404 с HTML, а не JSON.
"""

from datetime import timedelta

from backend.tests.test_chart_access import _make_chart
from backend.time_utils import utcnow


def _make_shared_chart(db, share_name="Тестовая карта", expires_delta=timedelta(days=1)):
    chart = _make_chart(db)
    chart.public_token = "share-token-test"
    chart.share_name = share_name
    chart.public_token_expires_at = (
        utcnow() + expires_delta if expires_delta is not None else None
    )
    db.commit()
    db.refresh(chart)
    return chart


def test_valid_token_returns_200_with_name_in_og_title(client, db, monkeypatch):
    monkeypatch.setattr(
        "backend.share_router._get_share_quote",
        lambda *a, **kw: _async_return(""),
    )
    chart = _make_shared_chart(db, share_name="Мария")

    resp = client.get(f"/share/{chart.public_token}")

    assert resp.status_code == 200
    assert 'property="og:title"' in resp.text
    assert "Натальная карта · Мария" in resp.text
    assert resp.headers["content-type"].startswith("text/html")


def test_expired_token_returns_404_html_not_json(client, db, monkeypatch):
    monkeypatch.setattr(
        "backend.share_router._get_share_quote",
        lambda *a, **kw: _async_return(""),
    )
    chart = _make_shared_chart(db, expires_delta=timedelta(days=-1))

    resp = client.get(f"/share/{chart.public_token}")

    assert resp.status_code == 404
    assert resp.headers["content-type"].startswith("text/html")
    assert "Ссылка больше не действует" in resp.text
    # Аварийный путь — тот же случай, что раньше отдавал {"detail": ...}
    assert '"detail"' not in resp.text


def test_unknown_token_returns_404_html_not_json(client, db):
    resp = client.get("/share/does-not-exist")

    assert resp.status_code == 404
    assert resp.headers["content-type"].startswith("text/html")
    assert "Ссылка больше не действует" in resp.text


def test_error_pages_are_noindex(client, db):
    resp = client.get("/share/does-not-exist")
    assert 'name="robots" content="noindex, nofollow"' in resp.text


def test_valid_page_is_also_noindex(client, db, monkeypatch):
    monkeypatch.setattr(
        "backend.share_router._get_share_quote",
        lambda *a, **kw: _async_return(""),
    )
    chart = _make_shared_chart(db)

    resp = client.get(f"/share/{chart.public_token}")

    assert 'name="robots" content="noindex, nofollow"' in resp.text
    # noindex стоит РЯДОМ с OG-тегами, а не вместо них
    assert 'property="og:title"' in resp.text
    assert 'property="og:image"' in resp.text


async def _async_return(value):
    return value
