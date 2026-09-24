"""users.device_timezone — пояс устройства для уведомлений

Решение владельца 24.09.2026: «сегодня» и окно отправки уведомлений — по
поясу телефона (в вебе — браузера), пояс главной карты только запасной.
Клиент присылает пояс через PATCH /push/settings. NULL — пояс карты, то есть
поведение до этой миграции.

Revision ID: 056_user_device_timezone
Revises: 055_chart_utc_offset_manual
"""

from alembic import op
import sqlalchemy as sa

revision = "056_user_device_timezone"
down_revision = "055_chart_utc_offset_manual"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("device_timezone", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "device_timezone")
