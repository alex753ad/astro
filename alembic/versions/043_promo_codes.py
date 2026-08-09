"""promo_codes + promo_usages — таблицы для backend/admin/promo_router.py

Роутер купонов (создание, список, деактивация, применение при чекауте,
статистика, экспорт) написан целиком на raw SQL против этих двух таблиц, но
миграция для них так и не была добавлена — в файле остался только
TODO-комментарий с целевой схемой ("Миграция — добавить в Alembic
(015_promo_codes)"). Из-за этого КАЖДЫЙ вызов `/api/v1/admin/coupons*` и
`/api/v1/admin/export` падал с `OperationalError: no such table`.

Схема — как в комментарии promo_router.py, с одним исправлением: `user_id` в
promo_usages должен быть String(36), а не Integer — id пользователя в этом
проекте UUID-строка (`backend/models.py:User.id`), не auto-increment int.

Revision ID: 043_promo_codes
Revises: 042_admin_audit_log
"""
from alembic import op
import sqlalchemy as sa


revision = "043_promo_codes"
down_revision = "042_admin_audit_log"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "promo_codes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("discount_type", sa.String(length=10), nullable=False),
        sa.Column("discount_value", sa.Integer(), nullable=False),
        sa.Column("duration", sa.String(length=20), nullable=False),
        sa.Column("duration_months", sa.Integer(), nullable=True),
        sa.Column("applies_to_plans", sa.ARRAY(sa.String()), nullable=True),
        sa.Column("max_redemptions", sa.Integer(), nullable=True),
        sa.Column("times_redeemed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_promo_codes_code"), "promo_codes", ["code"], unique=True)

    op.create_table(
        "promo_usages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("promo_code", sa.String(length=32), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("plan", sa.String(length=20), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_promo_usages_promo_code"), "promo_usages", ["promo_code"])
    op.create_index(op.f("ix_promo_usages_user_id"), "promo_usages", ["user_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_promo_usages_user_id"), table_name="promo_usages")
    op.drop_index(op.f("ix_promo_usages_promo_code"), table_name="promo_usages")
    op.drop_table("promo_usages")
    op.drop_index(op.f("ix_promo_codes_code"), table_name="promo_codes")
    op.drop_table("promo_codes")
