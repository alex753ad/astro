"""Add lite tier — no-op for String columns, documents intent.

If the project ever migrates to a PostgreSQL ENUM type, this is where
the ALTER TYPE would go. Currently tier is String(20) so 'lite' is
already a valid value without schema changes.

Revision ID: 006_add_lite_tier
Create Date: 2026-05-28
"""
from alembic import op

revision = '006_add_lite_tier'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # String(20) column — no schema change needed.
    # If this were a PG ENUM:
    # op.execute("ALTER TYPE subscription_tier ADD VALUE 'lite' AFTER 'free'")
    pass


def downgrade():
    pass
