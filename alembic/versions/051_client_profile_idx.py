"""client_profiles.astrologer_id — индекс (AUDIT 5.3)

Каждая ручка CRM фильтрует клиентов астролога через
`ClientProfile.astrologer_id == astrologer.id` — это граница
безопасности (изоляция клиентов между астрологами), проходимая на
КАЖДОМ запросе списка/карточки клиента, а не редкий отчёт: список
клиентов (crm/router.py, dashboard_router.py), дашборд, рассылки
(tasks.py). Без индекса каждый такой запрос — полный скан
client_profiles по всем астрологам сразу.

Идемпотентная миграция (guard через inspect), по образцу
046_partner_visits.

Revision ID: 051_client_profile_idx
Revises: 050_drop_stripe_sub_id

⚠️ Короткое имя ревизии не случайность — `alembic_version.version_num` это
`varchar(32)` (см. комментарий в 050_drop_stripe_sub_id.py). Не удлинять.
"""
from alembic import op
from sqlalchemy import inspect

revision = "051_client_profile_idx"
down_revision = "050_drop_stripe_sub_id"
branch_labels = None
depends_on = None

INDEX_NAME = "ix_client_profiles_astrologer_id"


def _index_exists(conn, table, index_name):
    return index_name in [ix["name"] for ix in inspect(conn).get_indexes(table)]


def upgrade() -> None:
    conn = op.get_bind()
    if not _index_exists(conn, "client_profiles", INDEX_NAME):
        op.create_index(INDEX_NAME, "client_profiles", ["astrologer_id"])


def downgrade() -> None:
    conn = op.get_bind()
    if _index_exists(conn, "client_profiles", INDEX_NAME):
        op.drop_index(INDEX_NAME, table_name="client_profiles")
