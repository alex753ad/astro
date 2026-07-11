"""Push notifications: subscriptions, sent-log, user prefs.

Revision ID: 031_push_notifications
Revises: 030_phone_email_nullable
Create Date: 2026-07-11
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

revision = "031_push_notifications"
down_revision = "030_phone_email_nullable"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)

    # ── users: push preference columns (идемпотентно) ──
    existing_cols = [c["name"] for c in inspector.get_columns("users")]

    if "push_daily_forecast" not in existing_cols:
        op.add_column("users", sa.Column(
            "push_daily_forecast", sa.Boolean(), nullable=False, server_default="true"))
    if "push_daily_time" not in existing_cols:
        op.add_column("users", sa.Column(
            "push_daily_time", sa.String(length=5), nullable=False, server_default="08:00"))
    if "push_planner" not in existing_cols:
        op.add_column("users", sa.Column(
            "push_planner", sa.Boolean(), nullable=False, server_default="true"))
    if "push_key_transits" not in existing_cols:
        op.add_column("users", sa.Column(
            "push_key_transits", sa.Boolean(), nullable=False, server_default="true"))

    tables = inspector.get_table_names()

    # ── push_subscriptions ──
    if "push_subscriptions" not in tables:
        op.create_table(
            "push_subscriptions",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.String(length=36),
                      sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("endpoint", sa.Text(), nullable=False),
            sa.Column("p256dh", sa.Text(), nullable=False),
            sa.Column("auth", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.UniqueConstraint("endpoint", name="uq_push_sub_endpoint"),
        )
        op.create_index("ix_push_subscriptions_user_id", "push_subscriptions", ["user_id"])

    # ── push_sent_log ──
    if "push_sent_log" not in tables:
        op.create_table(
            "push_sent_log",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.String(length=36),
                      sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("kind", sa.String(length=16), nullable=False),
            sa.Column("ref_key", sa.String(length=128), nullable=False),
            sa.Column("sent_at", sa.DateTime(), nullable=True),
            sa.UniqueConstraint("user_id", "kind", "ref_key", name="uq_push_sent_user_kind_ref"),
        )
        op.create_index("ix_push_sent_log_user_id", "push_sent_log", ["user_id"])


def downgrade():
    op.drop_table("push_sent_log")
    op.drop_table("push_subscriptions")
    op.drop_column("users", "push_key_transits")
    op.drop_column("users", "push_planner")
    op.drop_column("users", "push_daily_time")
    op.drop_column("users", "push_daily_forecast")
