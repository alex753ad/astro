"""Add name column to users table.

Revision ID: 008_add_users_name
Revises: 007_add_lite_tier
Create Date: 2026-05-28
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

revision = '008_add_users_name'
down_revision = '007_add_lite_tier'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    existing = [col["name"] for col in inspector.get_columns("users")]

    if "name" not in existing:
        op.add_column("users", sa.Column("name", sa.String(255), nullable=True))

    if "is_email_confirmed" not in existing:
        op.add_column("users", sa.Column(
            "is_email_confirmed", sa.Boolean(),
            nullable=False, server_default=sa.text("false")
        ))

    if "google_sub" not in existing:
        op.add_column("users", sa.Column("google_sub", sa.String(255), nullable=True))

    if "stripe_customer_id" not in existing:
        op.add_column("users", sa.Column("stripe_customer_id", sa.String(255), nullable=True))

    if "stripe_subscription_id" not in existing:
        op.add_column("users", sa.Column("stripe_subscription_id", sa.String(255), nullable=True))

    if "expert_mode" not in existing:
        op.add_column("users", sa.Column(
            "expert_mode", sa.Boolean(),
            nullable=False, server_default=sa.text("false")
        ))


def downgrade() -> None:
    for col in ("name", "is_email_confirmed", "google_sub",
                "stripe_customer_id", "stripe_subscription_id", "expert_mode"):
        op.drop_column("users", col)
