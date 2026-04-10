"""Initial schema: users, natal_charts, interpretations.

Revision ID: 001_initial
Revises:
Create Date: 2026-01-01 00:00:00
"""

from alembic import op
import sqlalchemy as sa

revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id",              sa.String(36),  primary_key=True),
        sa.Column("email",           sa.String(255), nullable=False, unique=True),
        sa.Column("hashed_password", sa.String(255), nullable=True),
        sa.Column("is_active",       sa.Boolean,     nullable=False, server_default="true"),
        sa.Column("tier",            sa.String(20),  nullable=False, server_default="free"),
        sa.Column("created_at",      sa.DateTime,    server_default=sa.func.now()),
        sa.Column("updated_at",      sa.DateTime,    server_default=sa.func.now()),
    )
    op.create_index("ix_users_email", "users", ["email"])

    op.create_table(
        "natal_charts",
        sa.Column("id",           sa.String(36),  primary_key=True),
        sa.Column("user_id",      sa.String(36),  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("label",        sa.String(255), nullable=True),
        sa.Column("birth_date",   sa.String(10),  nullable=False),
        sa.Column("birth_time",   sa.String(5),   nullable=True),
        sa.Column("birth_place",  sa.String(255), nullable=False),
        sa.Column("latitude",     sa.Float,       nullable=False),
        sa.Column("longitude",    sa.Float,       nullable=False),
        sa.Column("timezone",     sa.String(50),  nullable=False),
        sa.Column("utc_datetime", sa.DateTime,    nullable=False),
        sa.Column("time_unknown", sa.Boolean,     server_default="false"),
        sa.Column("planets",      sa.JSON,        nullable=False),
        sa.Column("houses",       sa.JSON,        nullable=False),
        sa.Column("aspects",      sa.JSON,        nullable=False),
        sa.Column("ascendant",    sa.JSON,        nullable=True),
        sa.Column("midheaven",    sa.JSON,        nullable=True),
        sa.Column("house_system", sa.String(20),  server_default="placidus"),
        sa.Column("created_at",   sa.DateTime,    server_default=sa.func.now()),
    )
    op.create_index("ix_natal_charts_user_id", "natal_charts", ["user_id"])

    op.create_table(
        "interpretations",
        sa.Column("id",           sa.String(36),  primary_key=True),
        sa.Column("chart_id",     sa.String(36),  sa.ForeignKey("natal_charts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("profile_hash", sa.String(64),  nullable=False),
        sa.Column("engine_used",  sa.String(50),  nullable=False),
        sa.Column("content",      sa.Text,        nullable=False),
        sa.Column("sections",     sa.JSON,        nullable=True),
        sa.Column("created_at",   sa.DateTime,    server_default=sa.func.now()),
    )
    op.create_index("ix_interpretations_chart_id",     "interpretations", ["chart_id"])
    op.create_index("ix_interpretations_profile_hash", "interpretations", ["profile_hash"])


def downgrade() -> None:
    op.drop_index("ix_interpretations_profile_hash", table_name="interpretations")
    op.drop_index("ix_interpretations_chart_id",     table_name="interpretations")
    op.drop_table("interpretations")

    op.drop_index("ix_natal_charts_user_id", table_name="natal_charts")
    op.drop_table("natal_charts")

    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
