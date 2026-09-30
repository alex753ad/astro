"""feature_flags — флаги функций (режим до публикации, CLAUDE.md п.9)

Revision ID: 069_feature_flags
Revises: 068_email_opt_out

Строка на флаг: mode off / all / users, user_ids — для режима users.
Нет строки — флаг выключен (backend/flags.py), поэтому таблицу ничем не
заполняем: новый флаг выключен, пока его не включат в админке.
"""

from alembic import op
import sqlalchemy as sa

revision = "069_feature_flags"
down_revision = "068_email_opt_out"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "feature_flags",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("mode", sa.String(8), nullable=False, server_default="off"),
        sa.Column("user_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("feature_flags")
