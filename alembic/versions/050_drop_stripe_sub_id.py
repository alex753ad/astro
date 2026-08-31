"""users.stripe_subscription_id — мёртвая колонка, удалить

AUDIT (28.08.2026): колонка жила в users с эпохи Stripe, удалённого как
мёртвый код 19.08.2026 (f3fc0a3). Проверено grep по backend/: ни одного
чтения или записи `user.stripe_subscription_id` / `User.stripe_subscription_id`
нигде — ни в коде, ни в тестах. users.stripe_customer_id (соседняя колонка)
остаётся: она живая, читается в /profile/subscription.

Не путать с Subscription.stripe_subscription_id (другая таблица) — та
активно используется (`/profile/subscription`, SubscriptionResponse,
test_profile.py) и в этой миграции не трогается.

Идемпотентная миграция (guard через inspect), по образцу 038_user_is_admin.

Revision ID: 050_drop_stripe_sub_id
Revises: 049_forgive_lost_interpretations

⚠️ Имя ревизии короче, чем можно было бы ожидать (не
"050_drop_user_stripe_subscription_id") — `alembic_version.version_num`
имеет тип `varchar(32)` (виден в CI: 049_forgive_lost_interpretations,
32 символа, — это не совпадение, а фактический потолок), длинное имя роняет
`check-migrations` с `StringDataRightTruncation`. Не удлинять обратно.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "050_drop_stripe_sub_id"
down_revision = "049_forgive_lost_interpretations"
branch_labels = None
depends_on = None


def _column_exists(conn, table, column):
    return column in [c["name"] for c in inspect(conn).get_columns(table)]


def upgrade() -> None:
    conn = op.get_bind()
    if _column_exists(conn, "users", "stripe_subscription_id"):
        op.drop_column("users", "stripe_subscription_id")


def downgrade() -> None:
    conn = op.get_bind()
    if not _column_exists(conn, "users", "stripe_subscription_id"):
        op.add_column(
            "users", sa.Column("stripe_subscription_id", sa.String(255), nullable=True)
        )
