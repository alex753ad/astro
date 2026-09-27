"""share_show_birth — дата и место на публичной странице только по выбору

Revision ID: 062_share_show_birth
Revises: 061_selfcheck_runs

server_default false: уже выданные ссылки переходят в режим «только знаки»
(решение владельца 27.09.2026).
"""

from alembic import op
import sqlalchemy as sa

revision = "062_share_show_birth"
down_revision = "061_selfcheck_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "natal_charts",
        sa.Column("share_show_birth", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("natal_charts", "share_show_birth")
