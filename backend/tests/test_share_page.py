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


def test_no_share_name_uses_sun_sign_not_duplicate_title(client, db, monkeypatch):
    """31.08.2026: без share_name заголовок дублировался в «Натальная карта ·
    Натальная карта» — ни один вызывающий на фронте не шлёт этот параметр
    при создании ссылки, то есть это был не крайний случай, а норма.
    """
    monkeypatch.setattr(
        "backend.share_router._get_share_quote",
        lambda *a, **kw: _async_return(""),
    )
    chart = _make_shared_chart(db, share_name=None)

    resp = client.get(f"/share/{chart.public_token}")

    assert resp.status_code == 200
    assert "Натальная карта · Натальная карта" not in resp.text
    assert "Натальная карта · " in resp.text
    # Sun в фикстуре — Gemini (см. _make_chart), знак в описании публичный.
    assert "Близнецы" in resp.text


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


class TestHeadRequests:
    """HEAD на обеих ручках шаринга.

    Причина существования: FastAPI, в отличие от Starlette, НЕ добавляет HEAD
    к GET-маршрутам (fastapi/routing.py:892 против starlette/routing.py:229-234),
    и обе ручки отвечали на HEAD 405 с `allow: GET`. Краулеры превью
    проверяют ресурс HEAD-запросом до GET — Telegram до GET не доходил, и
    превью не строилось при полностью исправных тегах и рабочей картинке.
    Отладка 01.09.2026 несколько заходов ушла в теги, кэш мессенджера и
    отправителя, а дело было в методе.
    """

    def test_head_share_page_returns_200_html(self, client, db, monkeypatch):
        monkeypatch.setattr(
            "backend.share_router._get_share_quote",
            lambda *a, **kw: _async_return(""),
        )
        chart = _make_shared_chart(db)

        resp = client.head(f"/share/{chart.public_token}")

        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/html")
        assert resp.content == b""

    def test_head_card_png_returns_200_image(self, client, db):
        chart = _make_shared_chart(db)

        resp = client.head(f"/share/{chart.public_token}/card.png")

        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"
        assert resp.content == b""

    def test_head_card_png_does_not_generate_anything(self, client, db, monkeypatch):
        """ГЛАВНЫЙ тест этого класса — он закрепляет причину раннего выхода.

        Без него `if request.method == "HEAD"` в share_card_png выглядит
        лишней веткой, и следующий рефакторинг снимет её как упрощение. А
        снятие означает, что каждый HEAD краулера оплачивает рендер PNG
        1080x1920 и запрос к LLM за подписью, хотя тело всё равно
        отбрасывается на уровне ASGI: ручка превью превращается в нагрузку.
        """
        called = {"quote": 0, "render": 0}

        async def _spy_quote(*a, **kw):
            called["quote"] += 1
            return ""

        def _spy_new(*a, **kw):
            called["render"] += 1
            raise AssertionError("рендер картинки при HEAD не должен вызываться")

        monkeypatch.setattr("backend.share_router._get_share_quote", _spy_quote)
        import PIL.Image
        monkeypatch.setattr(PIL.Image, "new", _spy_new)

        chart = _make_shared_chart(db)
        resp = client.head(f"/share/{chart.public_token}/card.png")

        assert resp.status_code == 200
        assert called == {"quote": 0, "render": 0}

    def test_head_matches_get_on_unknown_token(self, client, db):
        """Иначе ручка станет оракулом существования токенов."""
        for path in ("/share/does-not-exist", "/share/does-not-exist/card.png"):
            get_code = client.get(path).status_code
            head_code = client.head(path).status_code
            assert head_code == get_code, path
            assert head_code == 404, path

    def test_head_matches_get_on_expired_token(self, client, db, monkeypatch):
        monkeypatch.setattr(
            "backend.share_router._get_share_quote",
            lambda *a, **kw: _async_return(""),
        )
        chart = _make_shared_chart(db, expires_delta=timedelta(days=-1))

        for path in (
            f"/share/{chart.public_token}",
            f"/share/{chart.public_token}/card.png",
        ):
            assert client.head(path).status_code == client.get(path).status_code, path


async def _async_return(value):
    return value
