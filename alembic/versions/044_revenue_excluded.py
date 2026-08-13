"""users.revenue_excluded — ручное исключение из MRR

Идемпотентная миграция (guard через inspect), по образцу 038_user_is_admin.

Дополняет автоматическое исключение пилотных участников (pilot_started_at):
друзья, тестовые аккаунты, промо — тариф платный/выдан, но в доход считать
не нужно. Флаг ставится вручную из админки, tier не трогает.

Revision ID: 044_revenue_excluded
Revises: 043_promo_codes
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "044_revenue_excluded"
down_revision = "043_promo_codes"
branch_labels = None
depends_on = None


def _column_exists(conn, table, column):
    return column in [c["name"] for c in inspect(conn).get_columns(table)]


def upgrade() -> None:
    conn = op.get_bind()
    if not _column_exists(conn, "users", "revenue_excluded"):
        op.add_column(
            "users",
            sa.Column(
                "revenue_excluded", sa.Boolean(), nullable=False, server_default=sa.false()
            ),
        )


def downgrade() -> None:
    conn = op.get_bind()
    if _column_exists(conn, "users", "revenue_excluded"):
        op.drop_column("users", "revenue_excluded")
