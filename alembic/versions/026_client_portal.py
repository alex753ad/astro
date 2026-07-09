"""consultation assignment + client portal (026 / roadmap idea 10)

Revision ID: 026_client_portal
Revises: 025_client_status
Create Date: 2026-07-08

Adds:
  - consultations.assignment       (домашнее задание клиенту)
  - client_portal_access table     (публичный read-only портал по токену)
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "026_client_portal"
down_revision = "025_client_status"
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

    if not _column_exists(conn, "consultations", "assignment"):
        op.add_column("consultations", sa.Column("assignment", sa.Text(), nullable=True))

    if not _table_exists(conn, "client_portal_access"):
        op.create_table(
            "client_portal_access",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("client_id", sa.Integer(), nullable=False),
            sa.Column("token", sa.String(64), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["client_id"], ["client_profiles.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("client_id", name="uq_portal_client"),
            sa.UniqueConstraint("token", name="uq_portal_token"),
        )

    if _table_exists(conn, "client_portal_access"):
        if not _index_exists(conn, "client_portal_access", "ix_client_portal_access_client_id"):
            op.create_index("ix_client_portal_access_client_id", "client_portal_access", ["client_id"])
        if not _index_exists(conn, "client_portal_access", "ix_client_portal_access_token"):
            op.create_index("ix_client_portal_access_token", "client_portal_access", ["token"], unique=True)


def downgrade() -> None:
    conn = op.get_bind()

    if _table_exists(conn, "client_portal_access"):
        for ix in ("ix_client_portal_access_client_id", "ix_client_portal_access_token"):
            if _index_exists(conn, "client_portal_access", ix):
                op.drop_index(ix, table_name="client_portal_access")
        op.drop_table("client_portal_access")

    if _column_exists(conn, "consultations", "assignment"):
        op.drop_column("consultations", "assignment")
