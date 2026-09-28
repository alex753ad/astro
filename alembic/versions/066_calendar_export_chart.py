"""calendar_export_logs.chart_id — лимит карт для экспорта в Google Календарь

Revision ID: 066_calendar_export_chart
Revises: 065_usage_paid_period

Решение владельца 29.09.2026: на Веге экспорт — для одной карты, на Лире и
Орионе — для всех (TIER_FLAGS gcal_charts). Экспорт идёт из браузера прямо в
Google, сервер видит только журнал; по успешным строкам с chart_id считается,
сколько разных карт человек уже выгружал. Старые строки без карты не
считаются — ограничение начинается с нуля.
"""

import sqlalchemy as sa
from alembic import op

revision = "066_calendar_export_chart"
down_revision = "065_usage_paid_period"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("calendar_export_logs", sa.Column("chart_id", sa.String(36), nullable=True))
    op.create_index("ix_calendar_export_logs_chart_id", "calendar_export_logs", ["chart_id"])


def downgrade() -> None:
    op.drop_index("ix_calendar_export_logs_chart_id", table_name="calendar_export_logs")
    op.drop_column("calendar_export_logs", "chart_id")
