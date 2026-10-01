"""push_moon_phases: у новых пользователей выключено

Revision ID: 072_moon_phases_default_off
Revises: 071_push_sends

Решение владельца 01.10.2026: по умолчанию включены только «Прогноз дня»,
«Важные транзиты» и «Планер». Это обратный ход 063 (там умолчание стало
true). Уже заведённым значение не меняется — как и в 063: выключили они
его сами или получили умолчание, различить нельзя.
"""

from alembic import op
import sqlalchemy as sa

revision = "072_moon_phases_default_off"
down_revision = "071_push_sends"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("users", "push_moon_phases", server_default=sa.false())


def downgrade() -> None:
    op.alter_column("users", "push_moon_phases", server_default=sa.true())
