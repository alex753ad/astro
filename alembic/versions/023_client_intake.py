"""client intake forms (023 / roadmap idea 6)

Revision ID: 023_client_intake
Revises: 022_broadcast_auto_unsub
Create Date: 2026-07-08

Adds:
  - client_intake table — публичные анкеты по токену; сабмит падает в CRM,
    астролог конвертирует в client_profiles (карта считается автоматически).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "023_client_intake"
down_revision = "022_broadcast_auto_unsub"
branch_labels = None
depends_on = None


def _table_exists(conn, name: str) -> bool:
    return inspect(conn).has_table(name)


def _index_exists(conn, table: str, index: str) -> bool:
    return index in [i["name"] for i in inspect(conn).get_indexes(table)]


def upgrade() -> None:
    conn = op.get_bind()

    if not _table_exists(conn, "client_intake"):
        op.create_table(
            "client_intake",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("astrologer_id", sa.Integer(), nullable=False),
            sa.Column("token", sa.String(64), nullable=False),
            sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
            sa.Column("submitted_data", sa.JSON(), nullable=True),
            sa.Column("submitted_at", sa.DateTime(), nullable=True),
            sa.Column("client_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["astrologer_id"], ["astrologer_profiles.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["client_id"], ["client_profiles.id"], ondelete="SET NULL"),
            sa.UniqueConstraint("token", name="uq_client_intake_token"),
        )

    if _table_exists(conn, "client_intake"):
        if not _index_exists(conn, "client_intake", "ix_client_intake_astrologer_id"):
            op.create_index("ix_client_intake_astrologer_id", "client_intake", ["astrologer_id"])
        if not _index_exists(conn, "client_intake", "ix_client_intake_token"):
            op.create_index("ix_client_intake_token", "client_intake", ["token"], unique=True)


def downgrade() -> None:
    conn = op.get_bind()

    if _table_exists(conn, "client_intake"):
        for ix in ("ix_client_intake_astrologer_id", "ix_client_intake_token"):
            if _index_exists(conn, "client_intake", ix):
                op.drop_index(ix, table_name="client_intake")
        op.drop_table("client_intake")
