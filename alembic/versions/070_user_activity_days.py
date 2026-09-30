"""user_activity_days — активные дни для удержания D1/D7/D30

Revision ID: 070_user_activity_days
Revises: 069_feature_flags

Задним числом не заполняется (решение владельца 30.09.2026): удержание
считается только по людям, зарегистрированным с первого записанного дня
(metrics.compute_retention_weekly).
"""

from alembic import op
import sqlalchemy as sa

revision = "070_user_activity_days"
down_revision = "069_feature_flags"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_activity_days",
        sa.Column("user_id", sa.String(36),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("day", sa.Date(), primary_key=True),
        sa.Column("platform", sa.String(8), primary_key=True),
        sa.Column("flags", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.create_index("ix_user_activity_days_day", "user_activity_days", ["day"])


def downgrade() -> None:
    op.drop_index("ix_user_activity_days_day", table_name="user_activity_days")
    op.drop_table("user_activity_days")
