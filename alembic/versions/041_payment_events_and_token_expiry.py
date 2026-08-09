"""payment_events + сроки жизни публичных токенов

M-1: таблица payment_events — идемпотентность платёжных вебхуков в БД, а не
только в Redis (тот при недоступности пропускал повтор), плюс аудит платежей.

L-3: колонки со сроком жизни для публичных токенов — проверка в SQL не может
«открыться» при недоступном кэше. Обе NULL-able: существующие ссылки остаются
бессрочными и не ломаются.

Revision ID: 041_payment_events
Revises: 040_feedback_user_agent
"""
from alembic import op
import sqlalchemy as sa


revision = "041_payment_events"
down_revision = "040_feedback_user_agent"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "payment_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False, server_default="robokassa"),
        sa.Column("inv_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("tier", sa.String(length=20), nullable=True),
        sa.Column("period", sa.String(length=20), nullable=True),
        sa.Column("amount", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_payment_events_inv_id"), "payment_events", ["inv_id"], unique=True)
    op.create_index(op.f("ix_payment_events_user_id"), "payment_events", ["user_id"], unique=False)

    op.add_column("natal_charts", sa.Column("public_token_expires_at", sa.DateTime(), nullable=True))
    op.add_column("client_portal_access", sa.Column("expires_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("client_portal_access", "expires_at")
    op.drop_column("natal_charts", "public_token_expires_at")
    op.drop_index(op.f("ix_payment_events_user_id"), table_name="payment_events")
    op.drop_index(op.f("ix_payment_events_inv_id"), table_name="payment_events")
    op.drop_table("payment_events")
