"""client tags (029 / roadmap idea 19)

Revision ID: 029_client_tags
Revises: 028_author_interp
Create Date: 2026-07-08

Adds:
  - client_profiles.tags (JSON — свободные метки клиента)
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "029_client_tags"
down_revision = "028_author_interp"
branch_labels = None
depends_on = None


def _column_exists(conn, table: str, column: str) -> bool:
    return column in [c["name"] for c in inspect(conn).get_columns(table)]


def upgrade() -> None:
    conn = op.get_bind()
    if not _column_exists(conn, "client_profiles", "tags"):
        op.add_column("client_profiles", sa.Column("tags", sa.JSON(), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    if _column_exists(conn, "client_profiles", "tags"):
        op.drop_column("client_profiles", "tags")
