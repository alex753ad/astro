"""Add auth and Stripe columns to users.

Revision ID: 003_users_auth_stripe
Revises: 002_subscriptions
Create Date: 2026-01-01 00:00:01
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

revision = "003_users_auth_stripe"
down_revision = "002_subscriptions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    existing_columns = [col["name"] for col in inspector.get_columns("users")]

    if "google_sub" not in existing_columns:
        op.add_column("users", sa.Column("google_sub", sa.String, nullable=True))

    if "stripe_customer_id" not in existing_columns:
        op.add_column("users", sa.Column("stripe_customer_id", sa.String, nullable=True))

    if "tier" not in existing_columns:
        op.add_column("users", sa.Column("tier", sa.String, nullable=False, server_default="free"))

    if "is_email_confirmed" not in existing_columns:
        op.add_column("users", sa.Column("is_email_confirmed", sa.Boolean, nullable=False, server_default="false"))

    existing_indexes = [idx["name"] for idx in inspector.get_indexes("users")]

    if "ix_users_google_sub" not in existing_indexes:
        op.create_index("ix_users_google_sub", "users", ["google_sub"])

    if "ix_users_stripe_customer_id" not in existing_indexes:
        op.create_index("ix_users_stripe_customer_id", "users", ["stripe_customer_id"])


def downgrade() -> None:
    op.drop_index("ix_users_stripe_customer_id", table_name="users")
    op.drop_index("ix_users_google_sub", table_name="users")
    op.drop_column("users", "is_email_confirmed")
    op.drop_column("users", "tier")
    op.drop_column("users", "stripe_customer_id")
    op.drop_column("users", "google_sub")