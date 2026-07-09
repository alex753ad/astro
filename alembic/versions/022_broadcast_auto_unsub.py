"""broadcast auto flag + client unsubscribe (022)

Revision ID: 022_broadcast_auto_unsub
Revises: 021_broadcast
Create Date: 2026-07-08

Adds:
  - astrologer_profiles.broadcast_auto     (тумблер автоотправки 1-го числа)
  - client_profiles.unsubscribe_token      (публичный токен отписки)
  - client_profiles.broadcast_opt_out      (клиент отписался)
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "022_broadcast_auto_unsub"
down_revision = "021_broadcast"
branch_labels = None
depends_on = None


def _column_exists(conn, table: str, column: str) -> bool:
    return column in [c["name"] for c in inspect(conn).get_columns(table)]


def _index_exists(conn, table: str, index: str) -> bool:
    return index in [i["name"] for i in inspect(conn).get_indexes(table)]


def upgrade() -> None:
    conn = op.get_bind()

    if not _column_exists(conn, "astrologer_profiles", "broadcast_auto"):
        op.add_column(
            "astrologer_profiles",
            sa.Column("broadcast_auto", sa.Boolean(), nullable=False, server_default="false"),
        )

    if not _column_exists(conn, "client_profiles", "unsubscribe_token"):
        op.add_column("client_profiles", sa.Column("unsubscribe_token", sa.String(64), nullable=True))
    if not _index_exists(conn, "client_profiles", "ix_client_profiles_unsubscribe_token"):
        op.create_index(
            "ix_client_profiles_unsubscribe_token",
            "client_profiles", ["unsubscribe_token"], unique=True,
        )

    if not _column_exists(conn, "client_profiles", "broadcast_opt_out"):
        op.add_column(
            "client_profiles",
            sa.Column("broadcast_opt_out", sa.Boolean(), nullable=False, server_default="false"),
        )


def downgrade() -> None:
    conn = op.get_bind()

    if _column_exists(conn, "client_profiles", "broadcast_opt_out"):
        op.drop_column("client_profiles", "broadcast_opt_out")
    if _index_exists(conn, "client_profiles", "ix_client_profiles_unsubscribe_token"):
        op.drop_index("ix_client_profiles_unsubscribe_token", table_name="client_profiles")
    if _column_exists(conn, "client_profiles", "unsubscribe_token"):
        op.drop_column("client_profiles", "unsubscribe_token")
    if _column_exists(conn, "astrologer_profiles", "broadcast_auto"):
        op.drop_column("astrologer_profiles", "broadcast_auto")
