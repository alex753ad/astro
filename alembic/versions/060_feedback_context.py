"""feedback.context — версия, телефон и текст ошибки обращения из приложения

Revision ID: 060_feedback_context
Revises: 059_forecast_feedback
"""

from alembic import op
import sqlalchemy as sa

revision = "060_feedback_context"
down_revision = "059_forecast_feedback"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("feedback", sa.Column("context", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("feedback", "context")
