"""Add name column to natal_charts.

Revision ID: 010_natal_chart_name_col
Revises: 009_coupons_sent
Create Date: 2026-05-29
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

revision = '010_natal_chart_name_col'
down_revision = '009_coupons_sent'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    existing = [col["name"] for col in inspector.get_columns("natal_charts")]
    if "name" not in existing:
        op.add_column("natal_charts", sa.Column("name", sa.String(255), nullable=True))


def downgrade():
    op.drop_column("natal_charts", "name")
