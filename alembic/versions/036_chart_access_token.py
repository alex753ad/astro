"""natal_charts.access_token + expires_at (capability-доступ к анон-картам)

Идемпотентная миграция (guards через inspect).

Существующим анонимным картам проставляется access_token, но expires_at
остаётся NULL — они живут бессрочно. TTL действует только для карт,
созданных после релиза, чтобы не удалить данные пользователей, у которых
карта лежит в закладках.

Revision ID: 036_chart_access_token
Revises: 035_tg_pilot_entry
"""
import secrets

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "036_chart_access_token"
down_revision = "035_tg_pilot_entry"
branch_labels = None
depends_on = None


def _column_exists(conn, table, column):
    return column in [c["name"] for c in inspect(conn).get_columns(table)]


def _index_exists(conn, table, index):
    return index in [i["name"] for i in inspect(conn).get_indexes(table)]


def upgrade() -> None:
    conn = op.get_bind()

    if not _column_exists(conn, "natal_charts", "access_token"):
        op.add_column(
            "natal_charts", sa.Column("access_token", sa.String(length=64), nullable=True)
        )
    if not _column_exists(conn, "natal_charts", "expires_at"):
        op.add_column("natal_charts", sa.Column("expires_at", sa.DateTime(), nullable=True))

    # Бэкфилл: токен каждой существующей анонимной карте. Построчно, т.к.
    # значение должно быть уникальным и криптостойким.
    rows = conn.execute(
        sa.text(
            "SELECT id FROM natal_charts "
            "WHERE user_id IS NULL AND access_token IS NULL"
        )
    ).fetchall()
    for (chart_id,) in rows:
        conn.execute(
            sa.text("UPDATE natal_charts SET access_token = :tok WHERE id = :id"),
            {"tok": secrets.token_urlsafe(32), "id": chart_id},
        )

    if not _index_exists(conn, "natal_charts", "ix_natal_charts_access_token"):
        op.create_index(
            "ix_natal_charts_access_token", "natal_charts", ["access_token"], unique=True
        )
    if not _index_exists(conn, "natal_charts", "ix_natal_charts_expires_at"):
        op.create_index("ix_natal_charts_expires_at", "natal_charts", ["expires_at"])


def downgrade() -> None:
    conn = op.get_bind()
    for ix in ("ix_natal_charts_expires_at", "ix_natal_charts_access_token"):
        if _index_exists(conn, "natal_charts", ix):
            op.drop_index(ix, table_name="natal_charts")
    for col in ("expires_at", "access_token"):
        if _column_exists(conn, "natal_charts", col):
            op.drop_column("natal_charts", col)
