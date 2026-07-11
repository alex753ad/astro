"""make email nullable (phone reg support placeholder)

Revision ID: 030_phone_email_nullable
Revises: 029_client_tags
Create Date: 2026-07-11
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "030_phone_email_nullable"
down_revision = "029_client_tags"
branch_labels = None
depends_on = None


def _column_exists(conn, table: str, column: str) -> bool:
    return column in [c["name"] for c in inspect(conn).get_columns(table)]


def upgrade() -> None:
    conn = op.get_bind()

    # email → nullable
    op.alter_column(
        "users", "email",
        existing_type=sa.String(255),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "users", "email",
        existing_type=sa.String(255),
        nullable=False,
    )
