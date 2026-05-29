"""006_natal_chart_name

Add name column to natal_charts table.
"""
from alembic import op
import sqlalchemy as sa

revision = '006'
down_revision = '005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'natal_charts',
        sa.Column('name', sa.String(100), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('natal_charts', 'name')
