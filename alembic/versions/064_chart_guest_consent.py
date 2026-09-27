"""natal_charts: согласие гостя на обработку данных рождения

Revision ID: 064_chart_guest_consent
Revises: 063_digest_unsub_moon_default

Гость приложения и веб-лендинга вводит дату, время и место рождения до
регистрации. Галочка согласия записывается на карту и остаётся на ней после
привязки к аккаунту (решение владельца 27.09.2026).
"""

from alembic import op
import sqlalchemy as sa

revision = "064_chart_guest_consent"
down_revision = "063_digest_unsub_moon_default"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("natal_charts", sa.Column("consent_given_at", sa.DateTime(), nullable=True))
    op.add_column("natal_charts", sa.Column("consent_privacy_version", sa.String(20), nullable=True))


def downgrade() -> None:
    op.drop_column("natal_charts", "consent_privacy_version")
    op.drop_column("natal_charts", "consent_given_at")
