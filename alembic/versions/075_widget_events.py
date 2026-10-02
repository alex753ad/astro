"""widget_events — показы предложения поставить виджет и добавления

Revision ID: 075_widget_events
Revises: 074_story_card

Решение владельца 02.10.2026: показы и добавления виджета — в еженедельную
сводку (docs/widget_pin_card_plan.md, metrics._widget_line).
"""

from alembic import op
import sqlalchemy as sa

revision = "075_widget_events"
down_revision = "074_story_card"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "widget_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(36),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(8), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_widget_events_user_id", "widget_events", ["user_id"])
    op.create_index("ix_widget_events_created_at", "widget_events", ["created_at"])


def downgrade() -> None:
    op.drop_table("widget_events")
