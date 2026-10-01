"""push_sends — один содержательный пуш, одна строка (лимит 2 в сутки)

Revision ID: 071_push_sends
Revises: 070_user_activity_days

Пишется только у людей с флагом push_day_event (docs/notifications.md,
«Главное событие дня и лимит пушей»). Задним числом не заполняется.
"""

from alembic import op
import sqlalchemy as sa

revision = "071_push_sends"
down_revision = "070_user_activity_days"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "push_sends",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(36),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("local_date", sa.Date(), nullable=False),
        sa.Column("slot", sa.String(16), nullable=False),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_push_sends_user_date", "push_sends", ["user_id", "local_date"])


def downgrade() -> None:
    op.drop_index("ix_push_sends_user_date", table_name="push_sends")
    op.drop_table("push_sends")
