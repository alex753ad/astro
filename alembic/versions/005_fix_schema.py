"""Fix schema discrepancies: engine_used→engine, utc_datetime nullable.

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
        op.execute("ALTER TABLE interpretations RENAME COLUMN engine_used TO engine")
    elif "engine" not in interp_cols and "engine_used" not in interp_cols:
        op.add_column(
            "interpretations",
            sa.Column("engine", sa.String(50), nullable=False, server_default="template"),
        )

    # ── natal_charts: utc_datetime make nullable ──────────────────────────────
    natal_cols = {col["name"]: col for col in inspector.get_columns("natal_charts")}
    if "utc_datetime" in natal_cols:
        op.alter_column("natal_charts", "utc_datetime",
                        existing_type=sa.DateTime(), nullable=True)


def downgrade() -> None:
    op.alter_column("natal_charts", "utc_datetime",
                    existing_type=sa.DateTime(), nullable=False)
    op.execute("ALTER TABLE interpretations RENAME COLUMN engine TO engine_used")
