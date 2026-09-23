"""email_sent_log — журнал писем онбординга и писем после покупки

До этой миграции письма day2/day7/day14 и lite_day14/pro_day30 ставились
отложенными задачами Celery (countdown до 30 суток). Задача с ETA дольше
visibility timeout Redis-брокера выдавалась воркеру заново каждый час, и
23.09.2026 одно письмо пришло ~10 раз разом. Письма day2/day7 вдобавок слал
второй путь — ручка /internal/onboarding-emails от даты регистрации.

Теперь путь один: Beat-задача `tasks.send_lifecycle_emails` выбирает «пора, ещё
не опоздали, нет в журнале». Эта миграция:

1. создаёт `email_sent_log` (user_id, kind, ref, sent_at) с уникальным индексом
   (user_id, kind, ref);
2. добавляет `payment_events.starts_chain` — оплата начала тариф, а не продлила;
3. ЗАПОЛНЯЕТ журнал по датам, чтобы после выката не ушла волна старых писем
   (решение владельца 23.09.2026). Данных о фактически отправленном нет нигде:
   Celery писал только ошибки, docker-логи ротируются, Redis-ключи дедупа жили
   сутки-месяц и о письмах до 23.09 ничего не знают. Поэтому правило — «срок
   уже наступил → считаем отправленным», sent_at = NULL (отправка не
   подтверждена). Кому срок ещё не наступил — записи нет, письмо пришлёт Beat.

starts_chain для старых платежей: первый УСПЕШНЫЙ платёж пользователя на этом
тарифе (решение владельца). Успешный = period не NULL (у непригодных NULL),
amount > 0 и inv_id не "refund:…" (строки возвратов).

Сроки дублируются здесь литералами намеренно: миграция фиксирует состояние на
момент выката и не должна меняться вслед за правкой констант в коде.

Revision ID: 054_email_sent_log
Revises: 053_device_tokens
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "054_email_sent_log"
down_revision = "053_device_tokens"
branch_labels = None
depends_on = None

# kind → через сколько суток от точки отсчёта письмо «пора»
_ONBOARDING_DUE_DAYS = {"retention_day2": 2, "retention_day7": 7, "retention_day14": 14}
_PURCHASE_DUE_DAYS = {"lite_day14": ("lite", 14), "pro_day30": ("pro", 30)}
_WELCOME_KIND = {"lite": "lite_welcome", "pro": "pro_welcome", "premium": "premium_welcome"}


def upgrade() -> None:
    conn = op.get_bind()
    insp = inspect(conn)

    if "email_sent_log" not in insp.get_table_names():
        op.create_table(
            "email_sent_log",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "user_id", sa.String(36),
                sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
            ),
            sa.Column("kind", sa.String(32), nullable=False),
            sa.Column("ref", sa.String(64), nullable=False, server_default=""),
            sa.Column("sent_at", sa.DateTime(), nullable=True),
            sa.UniqueConstraint("user_id", "kind", "ref", name="uq_email_sent_user_kind_ref"),
        )
        op.create_index("ix_email_sent_log_user_id", "email_sent_log", ["user_id"])

    if "starts_chain" not in [c["name"] for c in insp.get_columns("payment_events")]:
        op.add_column(
            "payment_events",
            sa.Column("starts_chain", sa.Boolean(), nullable=False, server_default=sa.false()),
        )

    # ── starts_chain: первый успешный платёж пользователя на тарифе ──
    conn.execute(sa.text("""
        UPDATE payment_events SET starts_chain = TRUE
        WHERE id IN (
            SELECT MIN(id) FROM payment_events
            WHERE user_id IS NOT NULL AND tier IS NOT NULL
              AND period IS NOT NULL AND amount > 0
              AND inv_id NOT LIKE 'refund:%'
            GROUP BY user_id, tier
        )
    """))

    # ── Журнал: онбординг, срок уже наступил ──
    # Наивный UTC, как хранятся created_at (backend/time_utils.utcnow). Не
    # CURRENT_TIMESTAMP: в Postgres это timestamptz, и сравнение с наивной
    # колонкой шло бы через TimeZone сессии — сдвиг на пояс сервера.
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for kind, days in _ONBOARDING_DUE_DAYS.items():
        conn.execute(
            sa.text("""
                INSERT INTO email_sent_log (user_id, kind, ref, sent_at)
                SELECT u.id, :kind, '', NULL FROM users u
                WHERE u.created_at IS NOT NULL AND u.created_at <= :cutoff
                  AND NOT EXISTS (
                    SELECT 1 FROM email_sent_log l
                    WHERE l.user_id = u.id AND l.kind = :kind AND l.ref = ''
                  )
            """),
            {"kind": kind, "cutoff": _minus_days(now, days)},
        )

    # ── Журнал: письма после покупки, срок уже наступил ──
    # Приветствие уходило через минуту после оплаты — считаем отправленным для
    # всех покупок, совершённых до выката.
    for tier, kind in _WELCOME_KIND.items():
        _backfill_purchase(conn, kind, tier, now)
    for kind, (tier, days) in _PURCHASE_DUE_DAYS.items():
        _backfill_purchase(conn, kind, tier, _minus_days(now, days))


def _minus_days(ts, days):
    from datetime import timedelta
    return ts - timedelta(days=days)


def _backfill_purchase(conn, kind, tier, cutoff):
    conn.execute(
        sa.text("""
            INSERT INTO email_sent_log (user_id, kind, ref, sent_at)
            SELECT p.user_id, :kind, CAST(p.id AS VARCHAR(64)), NULL
            FROM payment_events p
            JOIN users u ON u.id = p.user_id
            WHERE p.starts_chain = TRUE AND p.tier = :tier
              AND p.created_at IS NOT NULL AND p.created_at <= :cutoff
              AND NOT EXISTS (
                SELECT 1 FROM email_sent_log l
                WHERE l.user_id = p.user_id AND l.kind = :kind
                  AND l.ref = CAST(p.id AS VARCHAR(64))
              )
        """),
        {"kind": kind, "tier": tier, "cutoff": cutoff},
    )


def downgrade() -> None:
    conn = op.get_bind()
    insp = inspect(conn)
    if "starts_chain" in [c["name"] for c in insp.get_columns("payment_events")]:
        op.drop_column("payment_events", "starts_chain")
    if "email_sent_log" in insp.get_table_names():
        op.drop_index("ix_email_sent_log_user_id", table_name="email_sent_log")
        op.drop_table("email_sent_log")
