"""client status + source (025 / roadmap idea 8)

Revision ID: 025_client_status
Revises: 024_client_summary
Create Date: 2026-07-08

Adds:
  - client_profiles.status   (lead / active / regular / archived; default lead)
  - client_profiles.source   (откуда пришёл клиент)
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "025_client_status"
down_revision = "024_client_summary"
branch_labels = None
depends_on = None


def _column_exists(conn, table: str, column: str) -> bool:
    return column in [c["name"] for c in inspect(conn).get_columns(table)]


def upgrade() -> None:
    conn = op.get_bind()
    if not _column_exists(conn, "client_profiles", "status"):
        op.add_column(
            "client_profiles",
            sa.Column("status", sa.String(20), nullable=False, server_default="lead"),
        )
    if not _column_exists(conn, "client_profiles", "source"):
        op.add_column("client_profiles", sa.Column("source", sa.String(100), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    if _column_exists(conn, "client_profiles", "source"):
        op.drop_column("client_profiles", "source")
    if _column_exists(conn, "client_profiles", "status"):
        op.drop_column("client_profiles", "status")
