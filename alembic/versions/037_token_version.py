"""users.token_version — глобальная ревокация сессий

Идемпотентная миграция (guards через inspect).

Все пользователи стартуют с версии 0. Уже выданные токены не содержат claim
`tv` и читаются как версия 0, поэтому миграция не разлогинивает никого.

Revision ID: 037_token_version
Revises: 036_chart_access_token
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "037_token_version"
down_revision = "036_chart_access_token"
branch_labels = None
depends_on = None


def _column_exists(conn, table, column):
    return column in [c["name"] for c in inspect(conn).get_columns(table)]


def upgrade() -> None:
    conn = op.get_bind()
    if not _column_exists(conn, "users", "token_version"):
        op.add_column(
            "users",
            sa.Column(
                "token_version", sa.Integer(), nullable=False, server_default="0"
            ),
        )


def downgrade() -> None:
    conn = op.get_bind()
    if _column_exists(conn, "users", "token_version"):
        op.drop_column("users", "token_version")
