"""consultations (020)

Revision ID: 020_consultations
Revises: 019_usage_counters
Create Date: 2026-07-08

Adds:
  - consultations table — хронология консультаций клиента.
    Фундамент для брифа (2), дохода/статистики (9), ретеншена (16).
    Старое поле client_profiles.notes НЕ трогаем — остаётся как общие заметки о клиенте.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "020_consultations"
down_revision = "019_usage_counters"
branch_labels = None
depends_on = None


def _table_exists(conn, name: str) -> bool:
    return inspect(conn).has_table(name)


def _index_exists(conn, table: str, index: str) -> bool:
    idxs = [i["name"] for i in inspect(conn).get_indexes(table)]
    return index in idxs


def upgrade() -> None:
    conn = op.get_bind()

    if not _table_exists(conn, "consultations"):
        op.create_table(
            "consultations",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("client_id", sa.Integer(), nullable=False),
            sa.Column("date", sa.DateTime(), nullable=False),
            sa.Column("topic", sa.String(50), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("next_date", sa.DateTime(), nullable=True),
            sa.Column("price", sa.Integer(), nullable=True),
            sa.Column("status", sa.String(20), nullable=False, server_default="done"),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["client_id"], ["client_profiles.id"], ondelete="CASCADE"),
        )

    if _table_exists(conn, "consultations") and not _index_exists(
        conn, "consultations", "ix_consultations_client_id"
    ):
        op.create_index("ix_consultations_client_id", "consultations", ["client_id"])


def downgrade() -> None:
    conn = op.get_bind()

    if _table_exists(conn, "consultations"):
        if _index_exists(conn, "consultations", "ix_consultations_client_id"):
            op.drop_index("ix_consultations_client_id", table_name="consultations")
        op.drop_table("consultations")
