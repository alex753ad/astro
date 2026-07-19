"""astrea memory (layer 2)

Revision ID: 039_astrea_memory
Revises: 038_user_is_admin
Create Date: 2026-07-19

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "039_astrea_memory"
down_revision = "038_user_is_admin"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "astrea_memory",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("summary", sa.Text(), server_default="", nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )


def downgrade() -> None:
    op.drop_table("astrea_memory")
