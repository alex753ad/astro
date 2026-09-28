"""Счётчики платных тарифов — за оплаченный период, а не за календарный месяц

Revision ID: 065_usage_paid_period
Revises: 064_chart_guest_consent

Решение владельца 28.09.2026. Доступ даётся на 30 дней с даты оплаты, а
счётчики обнулялись 1-го числа: купивший 29 сентября получал два лимита за
несколько дней. Теперь окно счётчика — 30 дней от `subscriptions.usage_anchor`
(начало цепочки оплат: новая покупка или смена тарифа), см.
`auth/rate_limits.usage_window`.

* `usage_counters.period_ym` расширен: в нём теперь и ключ окна вида
  «2609291412.0», а не только «ГГГГ-ММ» и «ALL».
* Действующим подпискам якорь ставится так, чтобы окна заканчивались ровно
  в `current_period_end`: end − n·30 дн. Ключ окна новый, значит счётчик
  текущего окна начинается с нуля — никто ничего не теряет (в худшем случае
  получает больше того, что успел потратить в сентябре).
"""

import math
from datetime import datetime, timedelta

import sqlalchemy as sa
from alembic import op

revision = "065_usage_paid_period"
down_revision = "064_chart_guest_consent"
branch_labels = None
depends_on = None

WINDOW = timedelta(days=30)


def upgrade() -> None:
    op.add_column("subscriptions", sa.Column("usage_anchor", sa.DateTime(), nullable=True))
    with op.batch_alter_table("usage_counters") as batch:
        batch.alter_column("period_ym", type_=sa.String(32), existing_type=sa.String(7),
                           existing_nullable=False)

    bind = op.get_bind()
    now = datetime.utcnow()
    rows = bind.execute(sa.text(
        "select id, current_period_end from subscriptions "
        "where status = 'active' and current_period_end > :now"
    ), {"now": now}).fetchall()
    for sub_id, end in rows:
        n = max(1, math.ceil((end - now) / WINDOW))
        bind.execute(sa.text("update subscriptions set usage_anchor = :a where id = :id"),
                     {"a": end - n * WINDOW, "id": sub_id})


def downgrade() -> None:
    op.drop_column("subscriptions", "usage_anchor")
    # period_ym обратно не сужаем: в нём уже лежат ключи окон длиннее 7 символов.
