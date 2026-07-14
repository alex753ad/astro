"""Telegram pilot entry: users.tg_user_id + pilot_tokens

Идемпотентная миграция (guards через inspect).

Revision ID: 035_tg_pilot_entry
Revises: 034_pilot_epics_all
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "035_tg_pilot_entry"
down_revision = "034_pilot_epics_all"
branch_labels = None
depends_on = None


def _table_exists(conn, name):
    return inspect(conn).has_table(name)


def _column_exists(conn, table, column):
    return column in [c["name"] for c in inspect(conn).get_columns(table)]


def _index_exists(conn, table, index):
    return index in [i["name"] for i in inspect(conn).get_indexes(table)]


def upgrade() -> None:
    conn = op.get_bind()

    # ── users.tg_user_id ──
    if not _column_exists(conn, "users", "tg_user_id"):
        op.add_column("users", sa.Column("tg_user_id", sa.String(length=32), nullable=True))
    if not _index_exists(conn, "users", "ix_users_tg_user_id"):
        op.create_index("ix_users_tg_user_id", "users", ["tg_user_id"], unique=True)

    # ── pilot_tokens ──
    if not _table_exists(conn, "pilot_tokens"):
        op.create_table(
            "pilot_tokens",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("token", sa.String(length=64), nullable=False),
            sa.Column("tg_user_id", sa.String(length=32), nullable=False),
            sa.Column("used", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("used_by_user_id", sa.String(length=36), nullable=True),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["used_by_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
    if _table_exists(conn, "pilot_tokens"):
        if not _index_exists(conn, "pilot_tokens", "ix_pilot_tokens_token"):
            op.create_index("ix_pilot_tokens_token", "pilot_tokens", ["token"], unique=True)
        if not _index_exists(conn, "pilot_tokens", "ix_pilot_tokens_tg_user_id"):
            op.create_index("ix_pilot_tokens_tg_user_id", "pilot_tokens", ["tg_user_id"])


def downgrade() -> None:
    conn = op.get_bind()
    if _table_exists(conn, "pilot_tokens"):
        for ix in ("ix_pilot_tokens_tg_user_id", "ix_pilot_tokens_token"):
            if _index_exists(conn, "pilot_tokens", ix):
                op.drop_index(ix, table_name="pilot_tokens")
        op.drop_table("pilot_tokens")
    if _index_exists(conn, "users", "ix_users_tg_user_id"):
        op.drop_index("ix_users_tg_user_id", table_name="users")
    if _column_exists(conn, "users", "tg_user_id"):
        op.drop_column("users", "tg_user_id")
