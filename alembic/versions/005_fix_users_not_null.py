"""fix users not null constraints

Revision ID: 005_fix_users_not_null
Revises: 004_expert_mode
Create Date: 2026-05-27

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '005_fix_users_not_null'
down_revision: Union[str, None] = '006_natal_chart_name'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Set default values for existing NULL rows
    op.execute("UPDATE users SET is_active = true WHERE is_active IS NULL")
    op.execute("UPDATE users SET is_email_confirmed = false WHERE is_email_confirmed IS NULL")
    op.execute("UPDATE users SET tier = 'free' WHERE tier IS NULL")
    
    # Add NOT NULL constraints
    op.alter_column('users', 'is_active',
                    existing_type=sa.Boolean(),
                    nullable=False,
                    server_default=sa.text('true'))
    
    op.alter_column('users', 'is_email_confirmed',
                    existing_type=sa.Boolean(),
                    nullable=False,
                    server_default=sa.text('false'))
    
    op.alter_column('users', 'tier',
                    existing_type=sa.String(length=20),
                    nullable=False,
                    server_default='free')


def downgrade() -> None:
    op.alter_column('users', 'tier',
                    existing_type=sa.String(length=20),
                    nullable=True,
                    server_default=None)
    
    op.alter_column('users', 'is_email_confirmed',
                    existing_type=sa.Boolean(),
                    nullable=True,
                    server_default=None)
    
    op.alter_column('users', 'is_active',
                    existing_type=sa.Boolean(),
                    nullable=True,
                    server_default=None)
