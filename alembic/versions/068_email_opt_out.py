"""email_opt_out — общая отписка от информационных писем; токен у всех

Revision ID: 068_email_opt_out
Revises: 067_pdf_reports

Решение владельца 30.09.2026: один флаг на все информационные письма
(онбординг, после покупки, дайджест, лунное возвращение, важный транзит,
пилот). Служебные письма (коды, оплата) флаг не читают.

* email_opt_out переносит digest_opt_out: кто отписался от дайджеста, не
  получит и остальные информационные письма — он просил «хватит писем».
  digest_opt_out не удаляется (решение владельца): код его больше не читает.
* email_unsub_token раньше заводился при первой отправке дайджеста. Теперь
  ссылка отписки стоит в каждом информационном письме, и токен нужен до
  отправки у всех — заполняется здесь, новым пользователям ставит ORM
  (models.User) и server_default. gen_random_uuid() — встроенная функция
  Postgres 13+, криптостойкая; расширение pgcrypto не нужно.
"""

from alembic import op
import sqlalchemy as sa

revision = "068_email_opt_out"
down_revision = "067_pdf_reports"
branch_labels = None
depends_on = None

_NEW_TOKEN = sa.text("replace(gen_random_uuid()::text, '-', '')")


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("email_opt_out", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.execute("UPDATE users SET email_opt_out = digest_opt_out")
    op.execute("UPDATE users SET email_unsub_token = replace(gen_random_uuid()::text, '-', '') "
               "WHERE email_unsub_token IS NULL")
    op.alter_column("users", "email_unsub_token", server_default=_NEW_TOKEN)


def downgrade() -> None:
    op.alter_column("users", "email_unsub_token", server_default=None)
    op.drop_column("users", "email_opt_out")
