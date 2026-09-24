"""payment_events.paid_at — момент оплаты для чеков «Мой налог»

Revision ID: 058_payment_paid_at
Revises: 057_announcements
"""

from alembic import op
import sqlalchemy as sa

revision = "058_payment_paid_at"
down_revision = "057_announcements"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("payment_events", sa.Column("paid_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("payment_events", "paid_at")
