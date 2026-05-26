"""Fix schema discrepancies between models and migrations.

Changes:
  - interpretations: rename engine_used -> engine
  - natal_charts: utc_datetime set nullable=True
  - users: add name column (nullable)

Revision ID: 005_fix_schema
Revises: 004_expert_mode
Create Date: 2026-05-26
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

revision = "005_fix_schema"
down_revision = "004_expert_mode"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)

    # ── interpretations: engine_used → engine ────────────────────────────────
    interp_cols = [col["name"] for col in inspector.get_columns("interpretations")]

    if "engine_used" in interp_cols and "engine" not in interp_cols:
        op.alter_column(
            "interpretations",
            "engine_used",
            new_column_name="engine",
        )
    elif "engine" not in interp_cols:
        op.add_column(
            "interpretations",
            sa.Column("engine", sa.String(50), nullable=False, server_default="template"),
        )

    # ── users: add name column ────────────────────────────────────────────────
    user_cols = [col["name"] for col in inspector.get_columns("users")]

    if "name" not in user_cols:
        op.add_column(
            "users",
            sa.Column("name", sa.String(255), nullable=True),
        )

    # ── natal_charts: utc_datetime nullable ──────────────────────────────────
    # PostgreSQL не позволяет просто ALTER nullable без дефолта,
    # поэтому используем batch_alter_table
    with op.batch_alter_table("natal_charts") as batch_op:
        batch_op.alter_column(
            "utc_datetime",
            existing_type=sa.DateTime(),
            nullable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("natal_charts") as batch_op:
        batch_op.alter_column(
            "utc_datetime",
            existing_type=sa.DateTime(),
            nullable=False,
        )

    op.drop_column("users", "name")

    op.alter_column(
        "interpretations",
        "engine",
        new_column_name="engine_used",
    )
