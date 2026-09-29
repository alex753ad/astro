"""PDF по тарифам: тариф разбора, отчёты в фоне, кеш разделов

Revision ID: 067_pdf_reports
Revises: 066_calendar_export_chart

Решение владельца 29.09.2026 (docs/task_current.md, п. 6):

* interpretations.tier — для какого тарифа написан разбор. PDF берёт разбор
  не короче тарифа человека, иначе пишет новый. У старых строк NULL —
  глубину выводит backend/pdf_reports/sections.py по числу слов.
* pdf_reports — сборка идёт в Celery, файл лежит на диске (том pdf_reports в
  docker-compose), здесь только путь. Хранится 30 дней: чистка удаляет и
  файл, и строку. Файлы не в БД намеренно: их можно пересобрать, а бэкап
  (pg_dump) от них раздувался бы.
* pdf_section_cache — тексты аспектов (до смены версии промпта) и транзитов
  (раз в месяц на тариф) по карте. Повторная выгрузка из кеша лимит не
  списывает.
"""

import sqlalchemy as sa
from alembic import op

revision = "067_pdf_reports"
down_revision = "066_calendar_export_chart"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("interpretations", sa.Column("tier", sa.String(20), nullable=True))

    op.create_table(
        "pdf_reports",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chart_id", sa.String(36), sa.ForeignKey("natal_charts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tier", sa.String(20), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("progress", sa.Integer, nullable=False, server_default="0"),
        sa.Column("step", sa.String(80), nullable=True),
        sa.Column("fingerprint", sa.String(200), nullable=True),
        sa.Column("file_path", sa.String(255), nullable=True),
        sa.Column("pages", sa.Integer, nullable=True),
        sa.Column("cost_usd", sa.Float, nullable=True),
        sa.Column("charged", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("error", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("ready_at", sa.DateTime, nullable=True),
        sa.Column("expires_at", sa.DateTime, nullable=False),
        sa.Column("seen_at", sa.DateTime, nullable=True),
    )
    op.create_index("ix_pdf_reports_user_id", "pdf_reports", ["user_id"])
    op.create_index("ix_pdf_reports_chart_id", "pdf_reports", ["chart_id"])
    op.create_index("ix_pdf_reports_expires_at", "pdf_reports", ["expires_at"])

    op.create_table(
        "pdf_section_cache",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("chart_id", sa.String(36), sa.ForeignKey("natal_charts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("key", sa.String(80), nullable=False),
        sa.Column("content", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint("chart_id", "key", name="uq_pdf_section_cache_chart_key"),
    )


def downgrade() -> None:
    op.drop_table("pdf_section_cache")
    op.drop_index("ix_pdf_reports_expires_at", table_name="pdf_reports")
    op.drop_index("ix_pdf_reports_chart_id", table_name="pdf_reports")
    op.drop_index("ix_pdf_reports_user_id", table_name="pdf_reports")
    op.drop_table("pdf_reports")
    op.drop_column("interpretations", "tier")
