"""Add CRM tables: astrologer_profiles, client_profiles.

Revision ID: 013_crm
Revises: 012_digest_settings
Create Date: 2026-05-29
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

revision = '013_crm'
down_revision = '012_digest_settings'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    existing_tables = inspector.get_table_names()

    if "astrologer_profiles" not in existing_tables:
        op.create_table(
            "astrologer_profiles",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.String(36),
                      sa.ForeignKey("users.id", ondelete="CASCADE"),
                      nullable=False, unique=True),
            sa.Column("display_name", sa.String(100), nullable=True),
        )

    if "client_profiles" not in existing_tables:
        op.create_table(
            "client_profiles",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("astrologer_id", sa.Integer(),
                      sa.ForeignKey("astrologer_profiles.id", ondelete="CASCADE"),
                      nullable=False),
            sa.Column("name", sa.String(100), nullable=False),
            sa.Column("birth_date", sa.Date(), nullable=False),
            sa.Column("birth_time", sa.Time(), nullable=True),
            sa.Column("birth_place", sa.String(200), nullable=False),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("natal_chart_id", sa.String(36),
                      sa.ForeignKey("natal_charts.id", ondelete="SET NULL"),
                      nullable=True),
        )


def downgrade():
    op.drop_table("client_profiles")
    op.drop_table("astrologer_profiles")
