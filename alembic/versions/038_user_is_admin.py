"""users.is_admin — админ-роль в БД вместо списка email в окружении

Идемпотентная миграция (guards через inspect).

Бэкфилл: флаг проставляется адресам из ADMIN_EMAIL, чтобы действующие
администраторы не потеряли доступ при выкатке. После миграции переменная
ADMIN_EMAIL на проверку доступа больше не влияет.

Revision ID: 038_user_is_admin
Revises: 037_token_version
"""
import os

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "038_user_is_admin"
down_revision = "037_token_version"
branch_labels = None
depends_on = None


def _column_exists(conn, table, column):
    return column in [c["name"] for c in inspect(conn).get_columns(table)]


def upgrade() -> None:
    conn = op.get_bind()

    if not _column_exists(conn, "users", "is_admin"):
        op.add_column(
            "users",
            sa.Column(
                "is_admin", sa.Boolean(), nullable=False, server_default=sa.false()
            ),
        )

    emails = [e.strip() for e in os.getenv("ADMIN_EMAIL", "").split(",") if e.strip()]
    if emails:
        conn.execute(
            sa.text("UPDATE users SET is_admin = true WHERE email IN :emails").bindparams(
                sa.bindparam("emails", expanding=True)
            ),
            {"emails": emails},
        )


def downgrade() -> None:
    conn = op.get_bind()
    if _column_exists(conn, "users", "is_admin"):
        op.drop_column("users", "is_admin")
