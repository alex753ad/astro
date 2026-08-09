"""admin_audit_log — след админских действий над чужими аккаунтами

M-3: POST /api/v1/payments/admin/set-tier выдаёт любой тариф на 10 лет, а
DELETE /api/v1/admin/users/{id} удаляет аккаунт вместе с картами и платежами.
До этой таблицы обе операции не оставляли следа нигде, кроме docker-логов,
которые ротируются по 10 МБ × 3.

target_user_id намеренно БЕЗ внешнего ключа: запись про удаление пользователя
обязана пережить самого пользователя. У admin_id ключ есть, но с SET NULL —
удаление админа не должно стирать историю его действий.

Revision ID: 042_admin_audit_log
Revises: 041_payment_events
"""
from alembic import op
import sqlalchemy as sa


revision = "042_admin_audit_log"
down_revision = "041_payment_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "admin_audit_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("admin_id", sa.String(length=36), nullable=True),
        sa.Column("admin_email", sa.String(length=255), nullable=True),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("target_user_id", sa.String(length=36), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("ip", sa.String(length=45), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["admin_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_admin_audit_log_admin_id"), "admin_audit_log", ["admin_id"])
    op.create_index(op.f("ix_admin_audit_log_action"), "admin_audit_log", ["action"])
    op.create_index(
        op.f("ix_admin_audit_log_target_user_id"), "admin_audit_log", ["target_user_id"]
    )
    op.create_index(op.f("ix_admin_audit_log_created_at"), "admin_audit_log", ["created_at"])


def downgrade() -> None:
    op.drop_index(op.f("ix_admin_audit_log_created_at"), table_name="admin_audit_log")
    op.drop_index(op.f("ix_admin_audit_log_target_user_id"), table_name="admin_audit_log")
    op.drop_index(op.f("ix_admin_audit_log_action"), table_name="admin_audit_log")
    op.drop_index(op.f("ix_admin_audit_log_admin_id"), table_name="admin_audit_log")
    op.drop_table("admin_audit_log")
