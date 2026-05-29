"""Add referral fields to users.

Revision ID: 011_referral
Revises: 010_natal_chart_name_col
Create Date: 2026-05-29
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

revision = '011_referral'
down_revision = '010_natal_chart_name_col'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    existing = [col["name"] for col in inspector.get_columns("users")]

    if "referral_code" not in existing:
        op.add_column("users", sa.Column("referral_code", sa.String(16), nullable=True))
        op.create_unique_constraint("uq_users_referral_code", "users", ["referral_code"])

    if "referred_by" not in existing:
        op.add_column("users", sa.Column(
            "referred_by", sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True
        ))


def downgrade():
    op.drop_constraint("uq_users_referral_code", "users", type_="unique")
    op.drop_column("users", "referral_code")
    op.drop_column("users", "referred_by")
