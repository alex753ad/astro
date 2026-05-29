"""Add coupons_sent table.

Revision ID: 009_coupons_sent
Revises: 008_add_users_name
Create Date: 2026-05-29
"""
from alembic import op
import sqlalchemy as sa

revision = '009_coupons_sent'
down_revision = '008_add_users_name'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'coupons_sent',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'),
                  nullable=False, unique=True),
        sa.Column('coupon_id', sa.String(255), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )


def downgrade():
    op.drop_table('coupons_sent')
