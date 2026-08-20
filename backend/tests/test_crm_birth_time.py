"""tests/test_crm_birth_time.py — ClientProfile.birth_time: строка → Time.

20.08.2026: ClientProfile.birth_time — Column(Time), а create_client клал
туда сырую строку из ClientCreate.birth_time (Optional[str]) без парсинга.
Под Postgres проходило молча (сервер сам приводит текстовый TIME-литерал),
под SQLite падало TypeError — расхождение всплыло только в тестах на
rate-limit. Три места в crm/router.py (711-714, 814-817, 916) уже defensively
проверяют hasattr(x, "strftime") на этом поле — верный признак, что баг уже
кусал раньше. Покрывает fix: явный парсинг "ЧЧ:ММ" на входе.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.auth.passwords import hash_password
from backend.auth.jwt import create_token_pair
from backend.models import ClientProfile, User


def make_premium_user(db: Session, email: str = "crm_bt@example.com") -> User:
    user = User(
        email=email,
        hashed_password=hash_password("Password123!"),
        is_active=True,
        is_email_confirmed=True,
        tier="premium",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def auth_headers(user: User) -> dict:
    tokens = create_token_pair(user.id, user.email, user.tier)
    return {"Authorization": f"Bearer {tokens.access_token}"}


class TestClientBirthTimeParsing:
    def test_valid_time_stored_as_real_time_object(
        self, client: TestClient, db: Session, mock_calculator, mock_geo,
    ):
        user = make_premium_user(db)
        resp = client.post(
            "/api/v1/clients",
            json={
                "name": "Клиент", "birth_date": "1990-01-10",
                "birth_time": "14:30", "birth_place": "Moscow",
            },
            headers=auth_headers(user),
        )
        assert resp.status_code == 201, resp.text

        row = db.query(ClientProfile).filter(ClientProfile.name == "Клиент").first()
        assert row is not None
        assert row.birth_time is not None
        assert row.birth_time.strftime("%H:%M") == "14:30"

    def test_missing_birth_time_stays_none(
        self, client: TestClient, db: Session, mock_calculator, mock_geo,
    ):
        user = make_premium_user(db, "crm_bt_none@example.com")
        resp = client.post(
            "/api/v1/clients",
            json={"name": "Без времени", "birth_date": "1990-01-10", "birth_place": "Moscow"},
            headers=auth_headers(user),
        )
        assert resp.status_code == 201, resp.text

        row = db.query(ClientProfile).filter(ClientProfile.name == "Без времени").first()
        assert row.birth_time is None

    def test_malformed_time_returns_422_not_500(
        self, client: TestClient, db: Session,
    ):
        user = make_premium_user(db, "crm_bt_bad@example.com")
        resp = client.post(
            "/api/v1/clients",
            json={
                "name": "Плохое время", "birth_date": "1990-01-10",
                "birth_time": "не время", "birth_place": "Moscow",
            },
            headers=auth_headers(user),
        )
        assert resp.status_code == 422
        assert "ЧЧ:ММ" in resp.json()["detail"]

    def test_response_serializes_time_back_to_string(
        self, client: TestClient, db: Session, mock_calculator, mock_geo,
    ):
        """ClientOut.coerce_time — обратная конвертация time → строка для
        JSON-ответа; закрывает контракт целиком, не только запись."""
        user = make_premium_user(db, "crm_bt_roundtrip@example.com")
        resp = client.post(
            "/api/v1/clients",
            json={
                "name": "Круговой рейс", "birth_date": "1990-01-10",
                "birth_time": "09:05", "birth_place": "Moscow",
            },
            headers=auth_headers(user),
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["birth_time"] == "09:05"
