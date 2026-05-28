"""Fix remaining schema constraints detected by alembic autogenerate.

Changes:
  - subscriptions: remove timezone=True from DateTime columns
  - subscriptions: remove ix_subscriptions_stripe_sub index
  - users: fix NOT NULL on is_active, is_email_confirmed, tier
  - users: fix unique constraints (email unique index, google_sub, stripe_customer_id)

Revision ID: 006_fix_constraints
Revises: 005_fix_schema
Create Date: 2026-05-26
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

revision = "006_fix_constraints"
down_revision = "005_fix_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)

    # ── subscriptions: remove timezone from DateTime columns ─────────────────
    op.alter_column("subscriptions", "current_period_end",
                    existing_type=sa.DateTime(timezone=True),
                    type_=sa.DateTime(), existing_nullable=True)
    op.alter_column("subscriptions", "created_at",
                    existing_type=sa.DateTime(timezone=True),
                    type_=sa.DateTime(), existing_nullable=True)
    op.alter_column("subscriptions", "updated_at",
                    existing_type=sa.DateTime(timezone=True),
                    type_=sa.DateTime(), existing_nullable=True)

    # ── subscriptions: drop ix_subscriptions_stripe_sub if exists ────────────
    existing_indexes = [idx["name"] for idx in inspector.get_indexes("subscriptions")]
    if "ix_subscriptions_stripe_sub" in existing_indexes:
        op.drop_index("ix_subscriptions_stripe_sub", table_name="subscriptions")

    # ── users: fix NOT NULL constraints ──────────────────────────────────────
    user_cols = {col["name"]: col for col in inspector.get_columns("users")}

    if "is_active" in user_cols:
        op.alter_column("users", "is_active",
                        existing_type=sa.Boolean(),
                        nullable=False,
                        server_default=sa.text("true"))

    if "is_email_confirmed" in user_cols:
        op.alter_column("users", "is_email_confirmed",
                        existing_type=sa.Boolean(),
                        nullable=False,
                        server_default=sa.text("false"))

    if "tier" in user_cols:
        op.alter_column("users", "tier",
                        existing_type=sa.String(),
                        nullable=False,
                        server_default=sa.text("'free'"))

    # ── users: fix email unique index ─────────────────────────────────────────
    user_indexes = {idx["name"]: idx for idx in inspector.get_indexes("users")}

    if "ix_users_email" in user_indexes and not user_indexes["ix_users_email"].get("unique"):
        op.drop_index("ix_users_email", table_name="users")
        op.create_index("ix_users_email", "users", ["email"], unique=True)

    # ── users: drop old non-unique indexes, add unique constraints ────────────
    if "ix_users_google_sub" in user_indexes:
        op.drop_index("ix_users_google_sub", table_name="users")

    if "ix_users_stripe_customer_id" in user_indexes:
        op.drop_index("ix_users_stripe_customer_id", table_name="users")

    # Check if unique constraints already exist before adding
    user_uq = [c["name"] for c in inspector.get_unique_constraints("users")]

    if "uq_users_google_sub" not in user_uq:
        try:
            op.create_unique_constraint("uq_users_google_sub", "users", ["google_sub"])
        except Exception:
            pass

    if "uq_users_stripe_customer_id" not in user_uq:
        try:
            op.create_unique_constraint("uq_users_stripe_customer_id", "users", ["stripe_customer_id"])
        except Exception:
            pass

    # ── foreign keys: drop and recreate without ondelete inconsistency ────────
    # natal_charts.user_id FK
    fks_natal = {fk["name"]: fk for fk in inspector.get_foreign_keys("natal_charts")}
    for fk_name, fk in fks_natal.items():
        if fk.get("referred_table") == "users" and fk.get("constrained_columns") == ["user_id"]:
            if fk_name:
                op.drop_constraint(fk_name, "natal_charts", type_="foreignkey")
                op.create_foreign_key(fk_name, "natal_charts", "users", ["user_id"], ["id"])
            break

    # interpretations.chart_id FK
    fks_interp = {fk["name"]: fk for fk in inspector.get_foreign_keys("interpretations")}
    for fk_name, fk in fks_interp.items():
        if fk.get("referred_table") == "natal_charts" and fk.get("constrained_columns") == ["chart_id"]:
            if fk_name:
                op.drop_constraint(fk_name, "interpretations", type_="foreignkey")
                op.create_foreign_key(fk_name, "interpretations", "natal_charts", ["chart_id"], ["id"])
            break


def downgrade() -> None:
    op.alter_column("subscriptions", "current_period_end",
                    existing_type=sa.DateTime(),
                    type_=sa.DateTime(timezone=True), existing_nullable=True)
    op.alter_column("subscriptions", "created_at",
                    existing_type=sa.DateTime(),
                    type_=sa.DateTime(timezone=True), existing_nullable=True)
    op.alter_column("subscriptions", "updated_at",
                    existing_type=sa.DateTime(),
                    type_=sa.DateTime(timezone=True), existing_nullable=True)
