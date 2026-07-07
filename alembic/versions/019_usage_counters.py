"""usage counters + free interpretation flag (3.3 / 3.4a)

Revision ID: 019_usage_counters
Revises: 8604e6b498e0
Create Date: 2026-07-07

Adds:
  - users.free_interpretation_used  (3.3 — одна бесплатная интерпретация для Free навсегда)
  - usage_counters table            (persistent per-month counters: interpretation / transit_ai)
"""
from alembic import op
import sqlalchemy as sa


revision = "019_usage_counters"
down_revision = "8604e6b498e0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "free_interpretation_used",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )

    op.create_table(
        "usage_counters",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("period_ym", sa.String(7), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "user_id", "kind", "period_ym", name="uq_usage_user_kind_period"
        ),
    )
    op.create_index(
        "ix_usage_counters_user_id", "usage_counters", ["user_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_usage_counters_user_id", table_name="usage_counters")
    op.drop_table("usage_counters")
    op.drop_column("users", "free_interpretation_used")
