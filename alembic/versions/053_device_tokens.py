"""device_tokens — токены FCM для доставки пушей в мобильное приложение

Веб-пуши живут в `push_subscriptions` (endpoint + p256dh + auth). Сюда их
класть нельзя, и это не вкусовщина: у той таблицы все три поля объявлены
NOT NULL, то есть FCM-токен пришлось бы уложить в `endpoint` с фиктивными
ключами — после чего `send_web_push` честно попытался бы отправить его через
pywebpush и получил бы отказ, который снаружи неотличим от мёртвой подписки.

Отдельная таблица разводит два транспорта по разным дорогам, а общим у них
остаётся ровно то, что и должно быть общим: отбор событий, тексты и журнал
отправленного (`push_sent_log`).

`token` уникален, а не пара (user_id, token): один телефон — один токен FCM,
и если на нём сменился аккаунт, запись обязана ПЕРЕЕХАТЬ к новому
пользователю, а не удвоиться. Иначе прежний владелец продолжал бы получать
уведомления по чужой карте. Тот же приём уже применён в `/push/subscribe`.

Revision ID: 053_device_tokens
Revises: 052_push_quiet_from

⚠️ Короткое имя ревизии не случайность — `alembic_version.version_num` это
`varchar(32)` (см. комментарий в 050_drop_stripe_sub_id.py). Не удлинять.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "053_device_tokens"
down_revision = "052_push_quiet_from"
branch_labels = None
depends_on = None

TABLE_NAME = "device_tokens"


def _table_exists(conn, table):
    return table in inspect(conn).get_table_names()


def upgrade() -> None:
    conn = op.get_bind()
    if _table_exists(conn, TABLE_NAME):
        return

    op.create_table(
        TABLE_NAME,
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("token", sa.Text(), nullable=False, unique=True),
        sa.Column("platform", sa.String(length=16), nullable=False, server_default="android"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        # Обновляется при каждой перерегистрации. Нужен не для статистики:
        # по нему видно живые устройства, когда придётся разбираться, почему
        # человеку ничего не приходит.
        sa.Column("last_seen_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    conn = op.get_bind()
    if _table_exists(conn, TABLE_NAME):
        op.drop_table(TABLE_NAME)
