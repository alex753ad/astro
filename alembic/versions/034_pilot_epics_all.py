"""Pilot epics (E8/E9/E10/E11): pilot_started_at + events + feedback + exit_reasons

Идемпотентная миграция (guards через inspect) — безопасна, даже если таблицы
уже созданы через Base.metadata.create_all при старте приложения.

Revision ID: 034_pilot_epics_all
Revises: 033_sync_model_drift
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "034_pilot_epics_all"
down_revision = "033_sync_model_drift"
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

    # ── users.pilot_started_at ──
    if not _column_exists(conn, "users", "pilot_started_at"):
        op.add_column("users", sa.Column("pilot_started_at", sa.DateTime(), nullable=True))

    # ── events ──
    if not _table_exists(conn, "events"):
        op.create_table(
            "events",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("user_id", sa.String(length=36), nullable=True),
            sa.Column("name", sa.String(length=64), nullable=False),
            sa.Column("ts", sa.DateTime(), nullable=False),
            sa.Column("meta", sa.JSON(), nullable=True),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
    if _table_exists(conn, "events"):
        if not _index_exists(conn, "events", "ix_events_user_id"):
            op.create_index("ix_events_user_id", "events", ["user_id"])
        if not _index_exists(conn, "events", "ix_events_name"):
            op.create_index("ix_events_name", "events", ["name"])
        if not _index_exists(conn, "events", "ix_events_ts"):
            op.create_index("ix_events_ts", "events", ["ts"])

    # ── feedback ──
    if not _table_exists(conn, "feedback"):
        op.create_table(
            "feedback",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("user_id", sa.String(length=36), nullable=True),
            sa.Column("screen", sa.String(length=120), nullable=True),
            sa.Column("url", sa.String(length=500), nullable=True),
            sa.Column("message", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
    if _table_exists(conn, "feedback"):
        if not _index_exists(conn, "feedback", "ix_feedback_user_id"):
            op.create_index("ix_feedback_user_id", "feedback", ["user_id"])
        if not _index_exists(conn, "feedback", "ix_feedback_created_at"):
            op.create_index("ix_feedback_created_at", "feedback", ["created_at"])

    # ── exit_reasons ──
    if not _table_exists(conn, "exit_reasons"):
        op.create_table(
            "exit_reasons",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("user_id", sa.String(length=36), nullable=True),
            sa.Column("moment", sa.String(length=20), nullable=False),
            sa.Column("reason_code", sa.String(length=40), nullable=True),
            sa.Column("reason_text", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
    if _table_exists(conn, "exit_reasons"):
        if not _index_exists(conn, "exit_reasons", "ix_exit_reasons_user_id"):
            op.create_index("ix_exit_reasons_user_id", "exit_reasons", ["user_id"])
        if not _index_exists(conn, "exit_reasons", "ix_exit_reasons_moment"):
            op.create_index("ix_exit_reasons_moment", "exit_reasons", ["moment"])
        if not _index_exists(conn, "exit_reasons", "ix_exit_reasons_created_at"):
            op.create_index("ix_exit_reasons_created_at", "exit_reasons", ["created_at"])


def downgrade() -> None:
    conn = op.get_bind()
    for tbl, idxs in (
        ("exit_reasons", ["ix_exit_reasons_created_at", "ix_exit_reasons_moment", "ix_exit_reasons_user_id"]),
        ("feedback", ["ix_feedback_created_at", "ix_feedback_user_id"]),
        ("events", ["ix_events_ts", "ix_events_name", "ix_events_user_id"]),
    ):
        if _table_exists(conn, tbl):
            for ix in idxs:
                if _index_exists(conn, tbl, ix):
                    op.drop_index(ix, table_name=tbl)
            op.drop_table(tbl)
    if _column_exists(conn, "users", "pilot_started_at"):
        op.drop_column("users", "pilot_started_at")
