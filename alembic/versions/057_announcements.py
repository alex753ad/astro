"""announcements — баннер объявлений (смена цен, оферта п. 10.1)

Revision ID: 057_announcements
Revises: 056_user_device_timezone
"""

from alembic import op
import sqlalchemy as sa

revision = "057_announcements"
down_revision = "056_user_device_timezone"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "announcements",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("ref", sa.String(100), nullable=False, unique=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("link", sa.String(200), nullable=True),
        sa.Column("ends_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("announcements")
