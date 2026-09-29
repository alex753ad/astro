"""Контракт старых APK: какие запросы старых версий приложения сервер обязан держать.

APK, поставленный на телефон, не обновляется вместе с деплоем: человек живёт на
старой сборке неделями. Удалить или переименовать ручку, которую она зовёт, —
значит сломать ему экран без единой ошибки в наших логах (404 от несуществующей
ручки в Sentry не падает). Поэтому всё, на что опираются старые сборки, собрано
здесь одним списком (решение владельца 29.09.2026).

Откуда список. Все вызовы API мобильного клиента с первой сборки APK
(`a420537`, 04.09.2026) по сегодня: пути из собранного `dist-mobile` плюс пути,
удалённые из `frontend/src/{mobile,api,lib,hooks}` за это время
(`git log -p a420537^..HEAD`). Синастрия, соляр, релокация и CRM сюда не входят
намеренно: в приложении их нет, это веб, и они пока не работают (решение
владельца 29.09.2026).

⚠️ **Строгим контракт становится с первой сборки, выложенной в RuStore**
(решение владельца 29.09.2026). До публикации APK стоят только на
устройствах приёмки, у людей их нет, и ручку из списка можно убрать вместе с
её вызовом в клиенте. После публикации — только так, как написано ниже.

⚠️ Упал тест — это не повод поправить список. Это значит, что правка сломает
приложение у тех, кто его не обновил. Убирать строку — только решением
владельца, с датой и причиной в комментарии.

⚠️ Новая ручка, которую начал звать мобильный клиент, добавляется сюда в том же
коммите: со следующей сборки она тоже часть контракта.

Уже НЕ держим и не возвращаем (решение владельца 29.09.2026: сборки с этими
вызовами были только на устройствах приёмки):
* `GET /chart/{id}/forecast/today` — снят 24.09.2026 (`1ee3029`), его звал APK
  от 23.09; замена — `/forecast/day?date=`.
* `POST /chart/save-anonymous` — снят 27.09.2026 (`d4e50ad`); замена —
  `POST /chart/{id}/claim`.
"""

import json

import pytest

from backend.auth.router import REFRESH_COOKIE_NAME
from backend.tests.test_chart_access import _make_chart
from backend.tests.test_interpret_finish_reason import (  # noqa: F401 — фикстура
    _events,
    _sse_url,
    stream_with_reason,
)
from backend.tests.test_pdf_reports import _interp, lite  # noqa: F401 — фикстура

API = "/api/v1"

# (метод, путь) — имена параметров как в роутерах сервера.
OLD_APK_ROUTES = [
    # Вход и сессия (hooks/useAuth.jsx, api/client.js)
    ("POST", "/auth/register"),
    ("POST", "/auth/register/email/send-code"),
    ("POST", "/auth/register/email/verify"),
    ("POST", "/auth/login"),
    ("POST", "/auth/google"),
    ("POST", "/auth/refresh"),
    ("POST", "/auth/logout"),
    ("POST", "/auth/password/reset-code"),
    ("POST", "/auth/password/reset-verify"),
    ("POST", "/auth/sse-ticket"),
    ("GET", "/auth/me"),
    # Карта (mobile/lib/chartApi.js)
    ("POST", "/chart/calculate"),
    ("GET", "/chart/{chart_id}"),
    ("POST", "/chart/{chart_id}/claim"),
    ("POST", "/charts/{chart_id}/share"),
    ("GET", "/chart/{chart_id}/interpret"),
    # Лента, прогнозы, транзиты, чат
    ("GET", "/chart/{chart_id}/feed"),
    ("GET", "/chart/{chart_id}/forecast/day"),
    ("GET", "/chart/{chart_id}/forecast/lunation"),
    ("POST", "/chart/{chart_id}/forecast/feedback"),
    ("POST", "/chart/{chart_id}/transits/event/interpret"),
    ("POST", "/chart/{chart_id}/rag-chat"),
    ("GET", "/chart/{chart_id}/rag-chat/history"),
    # PDF: старый синхронный путь и фоновые отчёты (mobile/lib/pdfApi.js)
    ("POST", "/chart/{chart_id}/pdf"),
    ("POST", "/chart/{chart_id}/pdf-reports"),
    ("GET", "/chart/{chart_id}/pdf-reports"),
    ("GET", "/pdf-reports/{report_id}"),
    ("GET", "/pdf-reports/{report_id}/file"),
    # Профиль (mobile/lib/moreApi.js; /profile/settings — сборки до 27.09)
    ("GET", "/profile/charts"),
    ("DELETE", "/profile/charts/{chart_id}"),
    ("PATCH", "/profile/primary-chart"),
    ("GET", "/profile/history"),
    ("GET", "/profile/subscription"),
    ("GET", "/profile/referral"),
    ("GET", "/profile/settings"),
    ("PATCH", "/profile/settings"),
    # Уведомления
    ("POST", "/push/device"),
    ("DELETE", "/push/device"),
    ("GET", "/push/settings"),
    ("PATCH", "/push/settings"),
    ("GET", "/push/upcoming"),
    # Оплата (mobile/lib/payApi.js, lib/announcements.js)
    ("POST", "/payments/checkout"),
    ("GET", "/payments/status/{payment_id}"),
    ("GET", "/payments/history"),
    ("GET", "/payments/announcements"),
    # Обращение в поддержку (mobile/lib/supportBus.js)
    ("POST", "/feedback"),
]


def _served(app) -> set[tuple[str, str]]:
    return {
        (method.upper(), path)
        for path, ops in app.openapi()["paths"].items()
        for method in ops
    }


@pytest.mark.parametrize("method,path", OLD_APK_ROUTES, ids=lambda v: v)
def test_route_still_served(client, method, path):
    """Маршрут с тем же методом и тем же шаблоном пути есть на сервере.

    Сравнение по шаблону, а не запросом: так не нужны ни база, ни данные, а
    404 и 405 ловятся одинаково — переименованная ручка и сменённый метод.
    Запросом нельзя ещё и потому, что 404 здесь отдают и живые ручки на чужую
    карту.

    ⚠️ По схеме OpenAPI, а не по `app.routes`: в CI список маршрутов
    подключённых роутеров не содержит (тот же случай — test_lifecycle_emails,
    test_debug_routes), и по нему этот тест дал 40 ложных падений 29.09.2026,
    проходя локально. Ручка с include_in_schema=False в схему не попадает —
    её здесь держит test_no_new_routes_hidden_from_schema."""
    assert (method, API + path) in _served(client.app), f"{method} {path} больше не обслуживается"


# Скрытые из схемы ручки: файл → пути. Сверено 29.09.2026 — ни одна из них
# приложением не вызывается.
HIDDEN_FROM_SCHEMA = {
    "partners/router.py": {"/track-visit"},  # веб, учёт перехода по партнёрской ссылке
}


def test_no_new_routes_hidden_from_schema():
    """test_route_still_served смотрит в схему OpenAPI, а ручка с
    include_in_schema=False в неё не попадает. Окажись такой ручка из
    контракта — тест выше упал бы, но и после «починки» списка контракт
    перестал бы её видеть. Поэтому скрытые ручки перечислены явно: новая
    — сначала решить, вызывает ли её приложение, потом дописать сюда.

    По исходнику, а не по app.routes: в CI список маршрутов подключённых
    роутеров не содержит (см. test_route_still_served)."""
    import re
    from pathlib import Path

    backend = Path(__file__).resolve().parents[1]
    found: dict[str, set[str]] = {}
    for f in backend.rglob("*.py"):
        if "tests" in f.relative_to(backend).parts:
            continue
        text = f.read_text(encoding="utf-8")
        if "include_in_schema" not in text:
            continue
        # Декоратор ручки или include_router/APIRouter целиком — любой случай.
        for m in re.finditer(r"\((?P<args>[^()]*include_in_schema\s*=\s*False[^()]*)\)", text):
            path = re.search(r"[\"']([^\"']*)[\"']", m.group("args"))
            found.setdefault(f.relative_to(backend).as_posix(), set()).add(path.group(1) if path else "<без пути>")
    assert found == HIDDEN_FROM_SCHEMA, (
        f"скрытые из OpenAPI ручки изменились: {found}. Вызывает ли их приложение? "
        "Если да — контракт по схеме их не видит, нужна проверка запросом."
    )
    # Ни одна скрытая не совпадает с ручкой контракта.
    hidden = {p for ps in found.values() for p in ps}
    assert not any(path.endswith(h) for _, path in OLD_APK_ROUTES for h in hidden)


# ── Поведение, на которое опираются старые сборки ───────────────────────────
# Перенесено сюда 29.09.2026 из test_refresh_cookie.py,
# test_interpret_finish_reason.py и test_pdf_reports.py.


class TestLegacyRefreshBody:
    """refresh-токен в теле запроса и в теле ответа.

    Сборки до перехода на HttpOnly-куку шлют его телом и ждут обратно телом.
    Без этой ветки в момент деплоя разлогинились бы все, у кого открыта вкладка
    со старым бандлом."""

    def test_body_token_accepted_and_echoed(self, client, user_free):
        login = client.post(
            "/api/v1/auth/login",
            json={"email": user_free.email, "password": "Password123!"},
        )
        token = login.cookies.get(REFRESH_COOKIE_NAME)
        client.cookies.clear()

        resp = client.post("/api/v1/auth/refresh", json={"refresh_token": token})
        assert resp.status_code == 200
        # Старый клиент ждёт токен в теле — иначе он его потеряет.
        assert resp.json()["refresh_token"]


class TestOldClientsSurviveFinishReason:
    """Событие finish_reason в потоке разбора необязательное. Эти тесты
    описывают ровно то, на что смотрит разборщик старого клиента
    (`_connectSSE`), — чтобы правка события не сломала его незаметно."""

    def test_event_has_no_type_text_or_error(
        self, client, db, user_pro, auth_headers_pro, stream_with_reason
    ):
        """Три ключа, по которым _connectSSE ветвится. Появись любой из них в
        этом событии — старый клиент принял бы служебное сообщение за часть
        разбора или за ошибку."""
        chart = _make_chart(db, user_id=user_pro.id)
        body = client.get(_sse_url(chart.id), headers=auth_headers_pro).text
        payload = next(
            json.loads(e) for e in _events(body)
            if e != "[DONE]" and "finish_reason" in e
        )
        assert set(payload) == {"finish_reason"}

    def test_done_marker_is_untouched(
        self, client, db, user_pro, auth_headers_pro, stream_with_reason
    ):
        """[DONE] сравнивается клиентом со строкой целиком — он обязан
        остаться ровно таким же."""
        chart = _make_chart(db, user_id=user_pro.id)
        body = client.get(_sse_url(chart.id), headers=auth_headers_pro).text
        assert "data: [DONE]\n\n" in body

    def test_text_events_unchanged(
        self, client, db, user_pro, auth_headers_pro, stream_with_reason
    ):
        """Сам разбор приходит теми же событиями, что и раньше."""
        chart = _make_chart(db, user_id=user_pro.id)
        body = client.get(_sse_url(chart.id), headers=auth_headers_pro).text
        texts = [
            json.loads(e).get("text") for e in _events(body)
            if e != "[DONE]" and "text" in e
        ]
        assert "".join(t for t in texts if t) == "Первая часть. Вторая часть."


def test_sync_pdf_still_answers_with_bytes(client, db, lite, auth_headers_free, monkeypatch):
    """Старые APK и старый веб шлют POST /chart/{id}/pdf и ждут байты PDF в
    ответе — ручка остаётся (решение владельца 29.09.2026)."""
    monkeypatch.setattr("backend.natal_pdf.generate_pdf_bytes", lambda *a, **kw: b"%PDF-1.4 test")
    chart = _make_chart(db, user_id=lite.id)
    _interp(db, chart, 800, tier="lite")
    r = client.post(f"/api/v1/chart/{chart.id}/pdf", headers=auth_headers_free)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF")
