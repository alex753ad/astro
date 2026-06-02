"""Add note_templates table.

Revision ID: 016_note_templates
Revises: 014_gift_codes
Create Date: 2026-06-02
"""
from alembic import op
import sqlalchemy as sa


revision = '016_note_templates'
down_revision = '014_gift_codes'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'note_templates',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_note_templates_user_id', 'note_templates', ['user_id'])


def downgrade():
    op.drop_index('ix_note_templates_user_id', table_name='note_templates')
    op.drop_table('note_templates')
