"""Add gift_codes table.

Revision ID: 014_gift_codes
Revises: 013_crm
Create Date: 2026-05-29
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

revision = '014_gift_codes'
down_revision = '013_crm'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    existing_tables = inspector.get_table_names()

    if "gift_codes" not in existing_tables:
        op.create_table(
            "gift_codes",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("code", sa.String(16), nullable=False, unique=True),
            sa.Column("tier", sa.String(20), nullable=False),
            sa.Column("duration_months", sa.Integer(), nullable=False),
            sa.Column("purchased_by", sa.String(36),
                      sa.ForeignKey("users.id", ondelete="SET NULL"),
                      nullable=True),
            sa.Column("redeemed_by", sa.String(36),
                      sa.ForeignKey("users.id", ondelete="SET NULL"),
                      nullable=True),
            sa.Column("redeemed_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
        )


def downgrade():
    op.drop_table("gift_codes")
