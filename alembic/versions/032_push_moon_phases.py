"""Add push_moon_phases to users.

Revision ID: 032_push_moon_phases
Revises: 031_push_notifications
Create Date: 2026-07-11
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

revision = "032_push_moon_phases"
down_revision = "031_push_notifications"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    existing = [c["name"] for c in inspector.get_columns("users")]
    if "push_moon_phases" not in existing:
        op.add_column("users", sa.Column(
            "push_moon_phases", sa.Boolean(), nullable=False, server_default="false"
        ))


def downgrade():
    op.drop_column("users", "push_moon_phases")
