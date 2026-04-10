"""add expert_mode to users

Revision ID: 004_expert_mode
Revises: 003_users_auth_stripe
Create Date: 2025-04-08
"""

from alembic import op
import sqlalchemy as sa

revision = "004_expert_mode"
down_revision = "003_users_auth_stripe"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "expert_mode",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "expert_mode")
