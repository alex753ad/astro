"""partner_visits — счётчик переходов по партнёрской ссылке

Идемпотентна (guard через inspect), по образцу 038_user_is_admin.

Revision ID: 046_partner_visits
Revises: 045_partners_and_commissions
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "046_partner_visits"
down_revision = "045_partners_and_commissions"
branch_labels = None
depends_on = None


def _table_exists(conn, table):
    return table in inspect(conn).get_table_names()


def upgrade() -> None:
    conn = op.get_bind()
    if not _table_exists(conn, "partner_visits"):
        op.create_table(
            "partner_visits",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("partner_id", sa.String(36), sa.ForeignKey("partners.id", ondelete="CASCADE"),
                      nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_partner_visits_partner_id", "partner_visits", ["partner_id"])
        op.create_index("ix_partner_visits_created_at", "partner_visits", ["created_at"])


def downgrade() -> None:
    conn = op.get_bind()
    if _table_exists(conn, "partner_visits"):
        op.drop_table("partner_visits")
