"""first_week_marks — что из первой недели человек уже открыл (флаг first_week)

Revision ID: 073_first_week_marks
Revises: 072_moon_phases_default_off

Решение владельца 01.10.2026 (backend/first_week.py). Задним числом не
заполняется: до флага отметок не было.
"""

from alembic import op
import sqlalchemy as sa

revision = "073_first_week_marks"
down_revision = "072_moon_phases_default_off"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "first_week_marks",
        sa.Column("user_id", sa.String(36),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("key", sa.String(16), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("first_week_marks")
