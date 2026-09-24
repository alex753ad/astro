"""forecast_feedback — 👍/👎 под прогнозом в приложении

Revision ID: 059_forecast_feedback
Revises: 058_payment_paid_at
"""

from alembic import op
import sqlalchemy as sa

revision = "059_forecast_feedback"
down_revision = "058_payment_paid_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "forecast_feedback",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chart_id", sa.String(36), sa.ForeignKey("natal_charts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("ref", sa.String(64), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("prompt_version", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("user_id", "chart_id", "kind", "ref", name="uq_forecast_feedback"),
    )
    op.create_index("ix_forecast_feedback_updated_at", "forecast_feedback", ["updated_at"])


def downgrade() -> None:
    op.drop_index("ix_forecast_feedback_updated_at", table_name="forecast_feedback")
    op.drop_table("forecast_feedback")
