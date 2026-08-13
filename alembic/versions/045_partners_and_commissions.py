"""partners, commissions, partner_payouts — партнёрская программа

Идемпотентна (guard через inspect), по образцу 038_user_is_admin.

Revision ID: 045_partners_and_commissions
Revises: 044_revenue_excluded
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "045_partners_and_commissions"
down_revision = "044_revenue_excluded"
branch_labels = None
depends_on = None


def _table_exists(conn, table):
    return table in inspect(conn).get_table_names()


def upgrade() -> None:
    conn = op.get_bind()

    if not _table_exists(conn, "partners"):
        op.create_table(
            "partners",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"),
                      nullable=False, unique=True),
            sa.Column("rate", sa.Float(), nullable=False, server_default="0.10"),
            sa.Column("started_at", sa.DateTime(), nullable=False),
            sa.Column("status", sa.String(20), nullable=False, server_default="active"),
            sa.Column("payout_details", sa.Text(), nullable=True),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_partners_user_id", "partners", ["user_id"])

    if not _table_exists(conn, "commissions"):
        op.create_table(
            "commissions",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("partner_id", sa.String(36), sa.ForeignKey("partners.id", ondelete="SET NULL"),
                      nullable=True),
            sa.Column("payment_event_id", sa.Integer(),
                      sa.ForeignKey("payment_events.id", ondelete="SET NULL"), nullable=True),
            sa.Column("amount", sa.Float(), nullable=False),
            sa.Column("rate", sa.Float(), nullable=True),
            sa.Column("kind", sa.String(20), nullable=False, server_default="earned"),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_commissions_partner_id", "commissions", ["partner_id"])
        op.create_index("ix_commissions_payment_event_id", "commissions", ["payment_event_id"])
        op.create_index("ix_commissions_created_at", "commissions", ["created_at"])

    if not _table_exists(conn, "partner_payouts"):
        op.create_table(
            "partner_payouts",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("partner_id", sa.String(36), sa.ForeignKey("partners.id", ondelete="SET NULL"),
                      nullable=True),
            sa.Column("admin_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"),
                      nullable=True),
            sa.Column("amount", sa.Float(), nullable=False),
            sa.Column("paid_at", sa.DateTime(), nullable=False),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_partner_payouts_partner_id", "partner_payouts", ["partner_id"])


def downgrade() -> None:
    conn = op.get_bind()
    if _table_exists(conn, "partner_payouts"):
        op.drop_table("partner_payouts")
    if _table_exists(conn, "commissions"):
        op.drop_table("commissions")
    if _table_exists(conn, "partners"):
        op.drop_table("partners")
