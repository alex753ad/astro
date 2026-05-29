"""Add digest_day_of_week to users.

Revision ID: 012_digest_settings
Revises: 011_referral
Create Date: 2026-05-29
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

revision = '012_digest_settings'
down_revision = '011_referral'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    existing = [col["name"] for col in inspector.get_columns("users")]

    if "digest_day_of_week" not in existing:
        op.add_column("users", sa.Column(
            "digest_day_of_week", sa.Integer(),
            nullable=False,
            server_default="0"
        ))


def downgrade():
    op.drop_column("users", "digest_day_of_week")
