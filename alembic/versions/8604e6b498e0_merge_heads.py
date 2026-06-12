"""merge_heads

Revision ID: 8604e6b498e0
Revises: 016_note_templates, 018_primary_chart
Create Date: 2026-06-12 10:26:25.255735

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8604e6b498e0'
down_revision = ('016_note_templates', '018_primary_chart')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
