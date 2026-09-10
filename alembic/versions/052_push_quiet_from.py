"""users.push_quiet_from — верхняя граница окна уведомлений

Парная настройка к `push_daily_time`. До неё у окна отправки была только
нижняя граница: планировщик (`backend/push/cron.py::_process_user`) проверял
`now_local < push_daily_time` и на этом заканчивал, то есть тик в 23:45
местного времени условие проходил и будил человека ночью. Ночью не будило
лишь потому, что дневное событие к этому моменту обычно уже отправлено и
отсеяно дедупом, — то есть держалось на побочном эффекте, а не на правиле.

Значение читают ДВА потребителя одной функцией `in_send_window`:
планировщик веб-пушей и ручка `GET /api/v1/push/upcoming`, отдающая
мобильному клиенту события для локального планирования. Второго источника
истины нет намеренно.

Дефолт "22:00" выбран так, чтобы окно по умолчанию (08:00–22:00) совпадало
с тем, в котором пуши фактически и уходили; существующим пользователям
поведение не меняется.

Идемпотентная миграция (guard через inspect), по образцу
051_client_profile_idx.

Revision ID: 052_push_quiet_from
Revises: 051_client_profile_idx

⚠️ Короткое имя ревизии не случайность — `alembic_version.version_num` это
`varchar(32)` (см. комментарий в 050_drop_stripe_sub_id.py). Не удлинять.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "052_push_quiet_from"
down_revision = "051_client_profile_idx"
branch_labels = None
depends_on = None

COLUMN_NAME = "push_quiet_from"


def _column_exists(conn, table, column):
    return column in [c["name"] for c in inspect(conn).get_columns(table)]


def upgrade() -> None:
    conn = op.get_bind()
    if not _column_exists(conn, "users", COLUMN_NAME):
        op.add_column(
            "users",
            sa.Column(
                COLUMN_NAME,
                sa.String(length=5),
                nullable=False,
                server_default="22:00",
            ),
        )


def downgrade() -> None:
    conn = op.get_bind()
    if _column_exists(conn, "users", COLUMN_NAME):
        op.drop_column("users", COLUMN_NAME)
