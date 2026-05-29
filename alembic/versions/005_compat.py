"""Compat stub: bridges short revision ID '005' used on production DB.

Revision ID: 005
Revises: 004_expert_mode
Create Date: 2026-05-29
"""
from alembic import op

revision = '005'
down_revision = '004_expert_mode'
branch_labels = None
depends_on = None


def upgrade():
    pass  # no-op — actual work is in 005_fix_users_not_null


def downgrade():
    pass
