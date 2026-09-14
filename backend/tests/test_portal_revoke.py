"""Отключение портала отзывает ссылку насовсем — находка аудита 2.6.

До правки `set_portal` менял только флаг `enabled`: токен оставался прежним,
`expires_at` не трогался. Значит выключение лишь ПРЯТАЛО портал, а следующее
включение возвращало ТУ ЖЕ ссылку — у клиента, которому доступ отобрали, она
снова начинала работать. Здесь проверяется, что старый токен после цикла
выкл/вкл мёртв, а новый живой.
"""

from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.auth.jwt import create_token_pair
from backend.auth.passwords import hash_password
from backend.models import AstrologerProfile, ClientProfile, User


def _astrologer_with_client(db: Session) -> tuple[dict, int]:
    user = User(
        email="portal_revoke@example.com",
        hashed_password=hash_password("Password123!"),
        is_active=True,
        is_email_confirmed=True,
        tier="premium",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    astrologer = AstrologerProfile(user_id=user.id, display_name="Астролог Ольга")
    db.add(astrologer)
    db.commit()
    db.refresh(astrologer)

    client_profile = ClientProfile(
        astrologer_id=astrologer.id,
        name="Мария Иванова",
        birth_date=date(1990, 6, 15),
        birth_place="Moscow",
    )
    db.add(client_profile)
    db.commit()
    db.refresh(client_profile)

    tokens = create_token_pair(user.id, user.email, user.tier)
    return {"Authorization": f"Bearer {tokens.access_token}"}, client_profile.id


def _toggle(client: TestClient, headers: dict, client_id: int, enabled: bool) -> dict:
    resp = client.post(
        f"/api/v1/clients/{client_id}/portal",
        json={"enabled": enabled},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


class TestPortalRevoke:
    def test_disable_then_enable_issues_new_link_and_kills_old(
        self, client: TestClient, db: Session,
    ):
        headers, client_id = _astrologer_with_client(db)

        old = _toggle(client, headers, client_id, True)
        assert client.get(f"/api/v1/portal/{old['token']}").status_code == 200

        _toggle(client, headers, client_id, False)
        new = _toggle(client, headers, client_id, True)

        assert new["token"] != old["token"]
        assert new["url"] != old["url"]
        # Старый токен не «спрятан», а стёрт: строка портала одна на клиента.
        assert client.get(f"/api/v1/portal/{old['token']}").status_code == 404
        assert client.get(f"/api/v1/portal/{new['token']}").status_code == 200

    def test_disabled_portal_is_closed_immediately(
        self, client: TestClient, db: Session,
    ):
        headers, client_id = _astrologer_with_client(db)

        old = _toggle(client, headers, client_id, True)
        _toggle(client, headers, client_id, False)

        assert client.get(f"/api/v1/portal/{old['token']}").status_code == 404

    def test_enable_refreshes_expiry(self, client: TestClient, db: Session):
        """Срок считается от включения — иначе портал, пролежавший
        выключенным дольше PORTAL_TTL_DAYS, включился бы уже просроченным.
        """
        from backend.models import ClientPortalAccess
        from backend.time_utils import utcnow

        headers, client_id = _astrologer_with_client(db)
        _toggle(client, headers, client_id, True)
        _toggle(client, headers, client_id, False)

        row = db.query(ClientPortalAccess).filter(
            ClientPortalAccess.client_id == client_id
        ).first()
        row.expires_at = utcnow().replace(year=utcnow().year - 1)
        db.commit()

        fresh = _toggle(client, headers, client_id, True)
        assert client.get(f"/api/v1/portal/{fresh['token']}").status_code == 200
