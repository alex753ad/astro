"""natal_charts.utc_offset_manual — смещение от UTC задано вручную

Человек видит, по какому смещению построена карта («UTC+3, по месту
рождения»), и может задать его сам. Число не хранится: оно выводится из
birth_date/birth_time и utc_datetime. Флаг нужен только чтобы подписать,
откуда оно взялось. Существующие карты — по месту (false), их расчёт не
меняется.

Revision ID: 055_chart_utc_offset_manual
Revises: 054_email_sent_log
"""

from alembic import op
import sqlalchemy as sa

revision = "055_chart_utc_offset_manual"
down_revision = "054_email_sent_log"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "natal_charts",
        sa.Column("utc_offset_manual", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("natal_charts", "utc_offset_manual")
