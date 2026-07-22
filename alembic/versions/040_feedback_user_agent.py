"""feedback.user_agent

Revision ID: 040_feedback_user_agent
Revises: 039_astrea_memory
Create Date: 2026-07-22

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "040_feedback_user_agent"
down_revision = "039_astrea_memory"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("feedback", sa.Column("user_agent", sa.String(300), nullable=True))


def downgrade() -> None:
    op.drop_column("feedback", "user_agent")
