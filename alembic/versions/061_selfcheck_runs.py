"""selfcheck_runs — итог каждого прогона самопроверки и сверки

Revision ID: 061_selfcheck_runs
Revises: 060_feedback_context
"""

from alembic import op
import sqlalchemy as sa

revision = "061_selfcheck_runs"
down_revision = "060_feedback_context"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "selfcheck_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("ran_at", sa.DateTime(), nullable=False),
        sa.Column("problems", sa.JSON(), nullable=True),
        sa.Column("unsent", sa.JSON(), nullable=True),
    )
    op.create_index("ix_selfcheck_runs_ran_at", "selfcheck_runs", ["ran_at"])


def downgrade() -> None:
    op.drop_index("ix_selfcheck_runs_ran_at", table_name="selfcheck_runs")
    op.drop_table("selfcheck_runs")
