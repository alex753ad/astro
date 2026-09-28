"""POST /api/v1/calendar/export-log — роутер существовал, но не был подключен.

AUDIT 1.3a, 28.08.2026: `calendar/export_router.py` объявляет ручку,
`include_router` для неё нет ни разу — фронт (`useGoogleCalendar.js:151`)
зовёт её fire-and-forget с `.catch(console.warn)`, 404 гасится в консоли,
таблица `calendar_export_logs` не наполняется никогда, метрика по экспорту в
Google Calendar не собирается вообще. Починка — `app.include_router(...)` в
main.py, схема запроса уже совпадала со схемой таблицы (models.py:497).
"""

from backend.models import CalendarExportLog


def test_export_log_endpoint_is_registered_not_404(client, auth_headers_free):
    """Раньше — 404 (роутер не подключён), теперь — 201 и запись в БД."""
    resp = client.post(
        "/api/v1/calendar/export-log",
        json={
            "month": "2026-09",
            "event_count": 3,
            "event_types": ["new_moon", "full_moon"],
            "status": "success",
        },
        headers=auth_headers_free,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json() == {"ok": True}


def test_export_log_persists_to_db(client, auth_headers_free, db, user_free):
    resp = client.post(
        "/api/v1/calendar/export-log",
        json={
            "month": "2026-10",
            "event_count": 0,
            "event_types": [],
            "status": "error",
            "error_msg": "quota exceeded",
        },
        headers=auth_headers_free,
    )
    assert resp.status_code == 201, resp.text

    row = (
        db.query(CalendarExportLog)
        .filter(CalendarExportLog.user_id == user_free.id)
        .first()
    )
    assert row is not None
    assert row.month == "2026-10"
    assert row.status == "error"
    assert row.error_msg == "quota exceeded"


def test_export_log_requires_auth(client):
    resp = client.post(
        "/api/v1/calendar/export-log",
        json={"month": "2026-09", "event_count": 1, "event_types": [], "status": "success"},
    )
    assert resp.status_code == 401


def test_export_log_rejects_bad_status(client, auth_headers_free):
    resp = client.post(
        "/api/v1/calendar/export-log",
        json={"month": "2026-09", "event_count": 1, "event_types": [], "status": "maybe"},
        headers=auth_headers_free,
    )
    assert resp.status_code == 422


# ── Лимит карт для экспорта (29.09.2026): Вега — одна, Лира и Орион — все ──

def _log(client, headers, chart_id, status="success"):
    return client.post("/api/v1/calendar/export-log", headers=headers, json={
        "month": "2026-10", "event_count": 3, "event_types": ["aspect"],
        "status": status, "chart_id": chart_id,
    })


def _allowed(client, headers, chart_id):
    return client.get(f"/api/v1/calendar/export-allowed?chart_id={chart_id}", headers=headers).json()


def _set_tier(db, user, tier):
    user.tier = tier
    db.commit()


def test_free_cannot_export(client, auth_headers_free):
    assert _allowed(client, auth_headers_free, "a")["allowed"] is False


def test_vega_one_chart_then_offers_lyra(client, db, user_free, auth_headers_free):
    _set_tier(db, user_free, "lite")
    assert _allowed(client, auth_headers_free, "a")["allowed"] is True
    _log(client, auth_headers_free, "a")
    assert _allowed(client, auth_headers_free, "a")["allowed"] is True      # ту же — можно
    r = _allowed(client, auth_headers_free, "b")
    assert r["allowed"] is False and "Лира" in r["reason"]
    _log(client, auth_headers_free, "c", status="error")                   # неудачный не считается
    assert _allowed(client, auth_headers_free, "a")["allowed"] is True


def test_lyra_all_charts(client, db, user_free, auth_headers_free):
    _set_tier(db, user_free, "pro")
    for cid in ("a", "b", "c"):
        _log(client, auth_headers_free, cid)
    assert _allowed(client, auth_headers_free, "d")["allowed"] is True
