"""author interpretations library (028 / roadmap idea 13)

Revision ID: 028_author_interp
Revises: 027_horary
Create Date: 2026-07-08

Adds:
  - astrologer_interpretations table (личная база трактовок астролога)
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "028_author_interp"
down_revision = "027_horary"
branch_labels = None
depends_on = None


def _table_exists(conn, name: str) -> bool:
    return inspect(conn).has_table(name)


def _index_exists(conn, table: str, index: str) -> bool:
    return index in [i["name"] for i in inspect(conn).get_indexes(table)]


def upgrade() -> None:
    conn = op.get_bind()
    if not _table_exists(conn, "astrologer_interpretations"):
        op.create_table(
            "astrologer_interpretations",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("astrologer_id", sa.Integer(), nullable=False),
            sa.Column("key", sa.String(100), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["astrologer_id"], ["astrologer_profiles.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("astrologer_id", "key", name="uq_author_interp_key"),
        )
    if _table_exists(conn, "astrologer_interpretations") and not _index_exists(
        conn, "astrologer_interpretations", "ix_astrologer_interpretations_astrologer_id"
    ):
        op.create_index(
            "ix_astrologer_interpretations_astrologer_id",
            "astrologer_interpretations", ["astrologer_id"],
        )


def downgrade() -> None:
    conn = op.get_bind()
    if _table_exists(conn, "astrologer_interpretations"):
        if _index_exists(conn, "astrologer_interpretations", "ix_astrologer_interpretations_astrologer_id"):
            op.drop_index("ix_astrologer_interpretations_astrologer_id", table_name="astrologer_interpretations")
        op.drop_table("astrologer_interpretations")
