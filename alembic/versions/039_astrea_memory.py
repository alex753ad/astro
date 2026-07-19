"""astrea memory (layer 2)

Revision ID: 039_astrea_memory
Revises: 038_user_is_admin
Create Date: 2026-07-19

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "039_astrea_memory"
down_revision = "038_user_is_admin"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS astrea_memory (
            user_id VARCHAR(36) NOT NULL,
            summary TEXT DEFAULT '' NOT NULL,
            updated_at TIMESTAMP WITHOUT TIME ZONE,
            PRIMARY KEY (user_id),
            FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
        )
    """)


def downgrade() -> None:
    op.drop_table("astrea_memory")
