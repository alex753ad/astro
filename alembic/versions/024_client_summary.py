"""client AI summary cache (024 / roadmap idea 7)

Revision ID: 024_client_summary
Revises: 023_client_intake
Create Date: 2026-07-08

Adds:
  - client_profiles.summary       (кэш AI-портрета клиента)
  - client_profiles.summary_key   (хэш заметок+консультаций+карты для инвалидации)
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "024_client_summary"
down_revision = "023_client_intake"
branch_labels = None
depends_on = None


def _column_exists(conn, table: str, column: str) -> bool:
    return column in [c["name"] for c in inspect(conn).get_columns(table)]


def upgrade() -> None:
    conn = op.get_bind()
    if not _column_exists(conn, "client_profiles", "summary"):
        op.add_column("client_profiles", sa.Column("summary", sa.Text(), nullable=True))
    if not _column_exists(conn, "client_profiles", "summary_key"):
        op.add_column("client_profiles", sa.Column("summary_key", sa.String(64), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    if _column_exists(conn, "client_profiles", "summary_key"):
        op.drop_column("client_profiles", "summary_key")
    if _column_exists(conn, "client_profiles", "summary"):
        op.drop_column("client_profiles", "summary")
