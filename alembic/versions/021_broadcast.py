"""client email + broadcast log (021 / roadmap idea 5)

Revision ID: 021_broadcast
Revises: 020_consultations
Create Date: 2026-07-08

Adds:
  - client_profiles.email        (nullable — адрес для ежемесячной рассылки)
  - client_broadcast_log table   (аудит + антидубли: одна успешная отправка на период)
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "021_broadcast"
down_revision = "020_consultations"
branch_labels = None
depends_on = None


def _table_exists(conn, name: str) -> bool:
    return inspect(conn).has_table(name)


def _column_exists(conn, table: str, column: str) -> bool:
    return column in [c["name"] for c in inspect(conn).get_columns(table)]


def _index_exists(conn, table: str, index: str) -> bool:
    return index in [i["name"] for i in inspect(conn).get_indexes(table)]


def upgrade() -> None:
    conn = op.get_bind()

    if not _column_exists(conn, "client_profiles", "email"):
        op.add_column("client_profiles", sa.Column("email", sa.String(255), nullable=True))

    if not _table_exists(conn, "client_broadcast_log"):
        op.create_table(
            "client_broadcast_log",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("astrologer_id", sa.Integer(), nullable=False),
            sa.Column("client_id", sa.Integer(), nullable=False),
            sa.Column("period_ym", sa.String(7), nullable=False),
            sa.Column("status", sa.String(10), nullable=False),
            sa.Column("sent_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["astrologer_id"], ["astrologer_profiles.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["client_id"], ["client_profiles.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("astrologer_id", "client_id", "period_ym", name="uq_broadcast_astro_client_period"),
        )

    if _table_exists(conn, "client_broadcast_log"):
        if not _index_exists(conn, "client_broadcast_log", "ix_client_broadcast_log_astrologer_id"):
            op.create_index("ix_client_broadcast_log_astrologer_id", "client_broadcast_log", ["astrologer_id"])
        if not _index_exists(conn, "client_broadcast_log", "ix_client_broadcast_log_client_id"):
            op.create_index("ix_client_broadcast_log_client_id", "client_broadcast_log", ["client_id"])


def downgrade() -> None:
    conn = op.get_bind()

    if _table_exists(conn, "client_broadcast_log"):
        for ix in ("ix_client_broadcast_log_astrologer_id", "ix_client_broadcast_log_client_id"):
            if _index_exists(conn, "client_broadcast_log", ix):
                op.drop_index(ix, table_name="client_broadcast_log")
        op.drop_table("client_broadcast_log")

    if _column_exists(conn, "client_profiles", "email"):
        op.drop_column("client_profiles", "email")
