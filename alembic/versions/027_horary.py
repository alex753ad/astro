"""horary fields on consultations (027 / roadmap idea 17)

Revision ID: 027_horary
Revises: 026_client_portal
Create Date: 2026-07-08

Adds:
  - consultations.question_moment  (момент вопроса)
  - consultations.question_place   (место вопроса)
  - consultations.horary_chart_id  (FK -> natal_charts, карта на момент вопроса)
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "027_horary"
down_revision = "026_client_portal"
branch_labels = None
depends_on = None


def _column_exists(conn, table: str, column: str) -> bool:
    return column in [c["name"] for c in inspect(conn).get_columns(table)]


def upgrade() -> None:
    conn = op.get_bind()
    if not _column_exists(conn, "consultations", "question_moment"):
        op.add_column("consultations", sa.Column("question_moment", sa.DateTime(), nullable=True))
    if not _column_exists(conn, "consultations", "question_place"):
        op.add_column("consultations", sa.Column("question_place", sa.String(200), nullable=True))
    if not _column_exists(conn, "consultations", "horary_chart_id"):
        op.add_column(
            "consultations",
            sa.Column("horary_chart_id", sa.String(36), nullable=True),
        )
        op.create_foreign_key(
            "fk_consultation_horary_chart", "consultations", "natal_charts",
            ["horary_chart_id"], ["id"], ondelete="SET NULL",
        )


def downgrade() -> None:
    conn = op.get_bind()
    if _column_exists(conn, "consultations", "horary_chart_id"):
        try:
            op.drop_constraint("fk_consultation_horary_chart", "consultations", type_="foreignkey")
        except Exception:
            pass
        op.drop_column("consultations", "horary_chart_id")
    if _column_exists(conn, "consultations", "question_place"):
        op.drop_column("consultations", "question_place")
    if _column_exists(conn, "consultations", "question_moment"):
        op.drop_column("consultations", "question_moment")
