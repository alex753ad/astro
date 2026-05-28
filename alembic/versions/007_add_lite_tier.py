"""Add lite tier — no-op for String(20) columns, documents intent.

Revision ID: 007_add_lite_tier
Revises: 006_share_token
Create Date: 2026-05-28
"""
from alembic import op

revision = '007_add_lite_tier'
down_revision = '006_share_token'
branch_labels = None
depends_on = None


def upgrade():
    # tier is String(20) — 'lite' is already valid without schema changes.
    # If this were a PG ENUM:
    # op.execute("ALTER TYPE subscription_tier ADD VALUE 'lite' AFTER 'free'")
    pass


def downgrade():
    pass
