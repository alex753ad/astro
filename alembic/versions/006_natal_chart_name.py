"""Compat stub: bridges revision '006_natal_chart_name' stored on production DB.

Revision ID: 006_natal_chart_name
Revises: 005
Create Date: 2026-05-29
"""
from alembic import op

revision = '006_natal_chart_name'
down_revision = '005'
branch_labels = None
depends_on = None


def upgrade():
    pass  # no-op — actual work is in subsequent migrations


def downgrade():
    pass
