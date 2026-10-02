"""story_card — счётчик отправок карточки дня и источник регистрации

Revision ID: 074_story_card
Revises: 073_first_week_marks

Решение владельца 01.10.2026 (флаг story_card, backend/story_card.py).
signup_source задним числом не заполняется: до этой правки источник не
записывался нигде.
"""

from alembic import op
import sqlalchemy as sa

revision = "074_story_card"
down_revision = "073_first_week_marks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("signup_source", sa.String(64), nullable=True))
    op.create_table(
        "story_card_shares",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(36),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("variant", sa.String(8), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_story_card_shares_user_id", "story_card_shares", ["user_id"])
    op.create_index("ix_story_card_shares_created_at", "story_card_shares", ["created_at"])


def downgrade() -> None:
    op.drop_table("story_card_shares")
    op.drop_column("users", "signup_source")
