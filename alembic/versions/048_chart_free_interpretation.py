"""natal_charts.free_interpretation_used — бесплатный разбор на каждую карту

До этого бесплатный разбор был один на аккаунт навсегда:
users.free_interpretation_used (019_usage_counters). При этом у Free два слота
под карты (profiles_limit = 2, см. CLAUDE.md), то есть человек имел право
построить вторую карту и не имел права её разобрать — право создать есть,
разобрать нельзя.

Ключ переезжает с аккаунта на карту. Потолок задаёт profiles_limit: два слота —
два разбора, отдельного счётчика нет и не нужно. Удаление карты возвращает
право по новой (строка исчезает вместе с картой), привязка анонимной карты
через /chart/save-anonymous ничего не отнимает — она вставляет новую строку
natal_charts, у неё флаг false.

users.free_interpretation_used НЕ удаляется и продолжает писаться: он больше не
гейт, но остаётся ответом на вопрос «разбирал ли пользователь хоть раз».

Почему флаг, а не подсчёт строк в interpretations: их пишут только два места,
оба про PDF (main.py:2161, tasks.py:401), а основной путь — SSE — не пишет
ничего. Считать было бы нечего. Плюс PDF-эндпоинт намеренно обходит проверку
лимита (решение владельца): при подсчёте строк он молча съедал бы право по
карте, при флаге — не трогает его вовсе, потому что флаг ставит только
commit_interpretation.

Существующие карты получают false, то есть по каждой уже сохранённой карте
появляется бесплатный разбор. Это и есть заявленное расширение.

Revision ID: 048_chart_free_interpretation
Revises: 047_consent_tracking
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "048_chart_free_interpretation"
down_revision = "047_consent_tracking"
branch_labels = None
depends_on = None


def _column_exists(conn, table, column):
    return column in [c["name"] for c in inspect(conn).get_columns(table)]


def upgrade() -> None:
    conn = op.get_bind()

    # server_default обязателен: колонка NOT NULL, а существующие строки надо
    # чем-то заполнить в том же выражении. Значение false = «разбора не было»,
    # то есть по каждой уже сохранённой карте разбор доступен.
    if not _column_exists(conn, "natal_charts", "free_interpretation_used"):
        op.add_column(
            "natal_charts",
            sa.Column(
                "free_interpretation_used",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )


def downgrade() -> None:
    conn = op.get_bind()
    if _column_exists(conn, "natal_charts", "free_interpretation_used"):
        op.drop_column("natal_charts", "free_interpretation_used")
