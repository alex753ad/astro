"""Флаги функций (backend/flags.py, docs/flags.md).

Здесь — сам механизм. Для каждой функции за флагом — свой тест в её файле:
с выключенным флагом функция не видна и не шлёт пушей и писем (шаблон —
docs/flags.md).
"""

import re
from pathlib import Path

import pytest

from backend import flags
from backend.auth.jwt import create_access_token
from backend.auth.passwords import hash_password
from backend.models import AdminAuditLog, User

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _fresh_cache():
    flags.reset_cache()
    yield
    flags.reset_cache()


@pytest.fixture
def admin_headers(db):
    admin = User(email="admin@example.com", hashed_password=hash_password("Password123!"),
                 name="Admin", tier="premium", is_admin=True)
    db.add(admin)
    db.commit()
    return {"Authorization": f"Bearer {create_access_token(user_id=admin.id, email=admin.email, tier=admin.tier)}"}


def _set(client, headers, mode, emails=()):
    return client.put("/api/v1/admin/flags/test_flag", headers=headers,
                      json={"mode": mode, "emails": list(emails)})


def _flags(client, headers=None):
    return client.get("/api/v1/flags", headers=headers or {}).json()["flags"]


def test_off_by_default(client, auth_headers_free):
    assert _flags(client) == []
    assert _flags(client, auth_headers_free) == []
    assert client.get("/api/v1/auth/me", headers=auth_headers_free).json()["flags"] == []


def test_users_mode_only_listed(client, admin_headers, user_free, auth_headers_free, auth_headers_pro):
    resp = _set(client, admin_headers, "users", [user_free.email.upper()])
    assert resp.status_code == 200, resp.text
    assert resp.json()["emails"] == [user_free.email]
    assert client.get("/api/v1/auth/me", headers=auth_headers_free).json()["flags"] == ["test_flag"]
    assert _flags(client, auth_headers_free) == ["test_flag"]
    assert _flags(client, auth_headers_pro) == []
    assert _flags(client) == []


def test_all_then_off(client, admin_headers, auth_headers_free):
    _set(client, admin_headers, "all")
    assert _flags(client) == ["test_flag"]
    assert _flags(client, auth_headers_free) == ["test_flag"]
    _set(client, admin_headers, "off")
    assert _flags(client) == []


def test_write_is_audited(client, db, admin_headers, user_free):
    _set(client, admin_headers, "users", [user_free.email])
    row = db.query(AdminAuditLog).filter_by(action="set_flag").one()
    assert row.details == {"key": "test_flag", "mode": "users", "emails": [user_free.email]}


def test_bad_input(client, admin_headers):
    assert _set(client, admin_headers, "users", ["nobody@example.com"]).status_code == 422
    assert _set(client, admin_headers, "users").status_code == 422
    assert _set(client, admin_headers, "maybe").status_code == 422
    assert client.put("/api/v1/admin/flags/no_such", headers=admin_headers,
                      json={"mode": "all"}).status_code == 404


def test_admin_only(client, auth_headers_free):
    assert client.get("/api/v1/admin/flags", headers=auth_headers_free).status_code == 403
    assert _set(client, auth_headers_free, "all").status_code == 403


def test_unknown_key_raises(db):
    with pytest.raises(KeyError):
        flags.flag_on(db, "no_such_flag", None)


def test_every_key_in_code_is_registered():
    """Ключ в flag_on(...) / useFlag('...') обязан быть в FLAGS — иначе
    функция молча выключена навсегда или падает на проде."""
    used = set()
    for path in [*ROOT.glob("backend/**/*.py"), *ROOT.glob("frontend/src/**/*.js*")]:
        if "tests" in path.parts or path.name.endswith((".test.js", ".test.jsx")):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        used |= set(re.findall(r"flag_on\(\s*\w+\s*,\s*[\"'](\w+)[\"']", text))
        used |= set(re.findall(r"useFlag\(\s*[\"'](\w+)[\"']", text))
    assert used <= set(flags.FLAGS), used - set(flags.FLAGS)
