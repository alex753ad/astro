"""add primary_chart_id to users

Revision ID: 018_primary_chart
Revises: 010_natal_chart_name_col
Create Date: 2026-06-12

"""
from alembic import op
import sqlalchemy as sa

revision = "018_primary_chart"
down_revision = "010_natal_chart_name_col"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("primary_chart_id", sa.String(36), nullable=True),
    )
    op.create_foreign_key(
        "fk_user_primary_chart",
        "users",
        "natal_charts",
        ["primary_chart_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_user_primary_chart", "users", type_="foreignkey")
    op.drop_column("users", "primary_chart_id")
