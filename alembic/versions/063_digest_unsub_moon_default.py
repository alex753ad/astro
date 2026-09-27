"""digest_opt_out + email_unsub_token; фазы Луны включены у новых

Revision ID: 063_digest_unsub_moon_default
Revises: 062_share_show_birth

* Отписка от недельного дайджеста по ссылке из письма (решение владельца
  27.09.2026).
* push_moon_phases: server_default true — у НОВЫХ пользователей все четыре
  вида уведомлений включены. Уже заведённым значение не меняется: выключили
  они его сами или получили старое умолчание — различить нельзя.
"""

from alembic import op
import sqlalchemy as sa

revision = "063_digest_unsub_moon_default"
down_revision = "062_share_show_birth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("digest_opt_out", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("users", sa.Column("email_unsub_token", sa.String(64), nullable=True))
    op.create_index("ix_users_email_unsub_token", "users", ["email_unsub_token"], unique=True)
    op.alter_column("users", "push_moon_phases", server_default=sa.true())


def downgrade() -> None:
    op.alter_column("users", "push_moon_phases", server_default=sa.false())
    op.drop_index("ix_users_email_unsub_token", table_name="users")
    op.drop_column("users", "email_unsub_token")
    op.drop_column("users", "digest_opt_out")
