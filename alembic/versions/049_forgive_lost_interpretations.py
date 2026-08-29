"""Простить бесплатный разбор там, где текста не осталось

До 30.08.2026 строку в interpretations писали только PDF-пути (main.py и
tasks.py). Основной, SSE-путь, не писал ничего: человек читал разбор на
экране, закрывал вкладку — и текст исчезал, а право на него было уже
потрачено (natal_charts.free_interpretation_used = true). Перечитать было
нечего и нечем.

Коммит bab8098 научил SSE-путь сохранять разбор, ce6d37c — отдавать его без
проверки лимита. Но карты, разобранные ДО этих коммитов, остались в тупике:
флаг стоит, строки нет, при открытии — отказ, а восстановить текст
неоткуда.

Миграция снимает флаг ровно с таких карт: право потрачено, а получить за
него нечего. Решение владельца 30.08.2026 — отдать право обратно.

── Почему условие именно такое и не нуждается в сужении ──────────────────
natal_charts.free_interpretation_used имеет РОВНО ОДНОГО писателя:
commit_interpretation (auth/rate_limits.py), ветка
`if limit == 0 and flags.get("first_interpretation_free")`. Оба условия
выполняются только у free (interpretations_per_month = 0 и
first_interpretation_free = True — только в TIER_FLAGS["free"]). Платные
тарифы этот флаг не пишут никогда и ни по какой другой причине, поэтому
дополнительной проверки тарифа не требуется.

Карта, разобранная на free и принадлежащая теперь платному тарифу, флаг
сохраняет. Снять его безвредно: для платных тарифов он не читается вовсе, а
при возврате на free право должно работать так же, как у всех остальных.

Анонимные карты (user_id IS NULL) под условие не попадают по построению:
commit_interpretation выходит раньше при user is None, то есть флаг у них
никогда не выставлялся.

⚠️ users.free_interpretation_used — ДРУГАЯ колонка, и она НЕ трогается.
Гейтом она давно не является, но остаётся ответом на вопрос «разбирал ли
пользователь хоть раз» и читается в get_feature_flags
(first_interpretation_available). Сбросить её значило бы соврать в этом
ответе.

Revision ID: 049_forgive_lost_interpretations
Revises: 048_chart_free_interpretation
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "049_forgive_lost_interpretations"
down_revision = "048_chart_free_interpretation"
branch_labels = None
depends_on = None


# Право потрачено, а текста за него нет. NOT EXISTS, а не NOT IN: последний
# возвращает пусто, если в подзапросе окажется хоть один NULL. Сегодня
# interpretations.chart_id объявлен NOT NULL, но полагаться на это в
# разовой правке прод-данных не стоит.
_ORPHANED = """
    FROM natal_charts c
    WHERE c.free_interpretation_used = true
      AND NOT EXISTS (
          SELECT 1 FROM interpretations i WHERE i.chart_id = c.id
      )
"""


def _table_exists(conn, table: str) -> bool:
    return table in inspect(conn).get_table_names()


def upgrade() -> None:
    conn = op.get_bind()

    # Обе таблицы должны существовать: на пустой базе (первый прогон с нуля)
    # миграции идут по порядку, но защищаемся от ручных прогонов на срезах.
    if not _table_exists(conn, "natal_charts") or not _table_exists(conn, "interpretations"):
        print("049: таблиц нет — пропускаю")
        return

    # Считаем ДО изменения: число уходит в вывод `alembic upgrade head`,
    # то есть в лог деплоя. Иначе узнать масштаб правки прод-данных
    # постфактум было бы неоткуда — сама правка следов не оставляет.
    affected = conn.execute(sa.text("SELECT COUNT(*) " + _ORPHANED)).scalar() or 0
    print(f"049: карт с потраченным правом и без сохранённого разбора — {affected}")

    if affected == 0:
        # Повторный прогон приходит сюда: после первого таких карт не
        # остаётся. Отдельного флага «уже применено» не нужно — условие
        # само себя исчерпывает.
        return

    conn.execute(sa.text("""
        UPDATE natal_charts
        SET free_interpretation_used = false
        WHERE id IN (SELECT c.id """ + _ORPHANED + ")"))
    print(f"049: право возвращено по {affected} картам")


def downgrade() -> None:
    """Откатить нельзя, и это не забывчивость.

    Чтобы вернуть флаг, надо знать, каким именно картам он был снят. Мы
    этого не записываем: правка идёт UPDATE-ом по условию, отдельной
    отметки «этой карте простили» в схеме нет.

    Поставить флаг обратно всем картам без строки в interpretations —
    неверно: под это условие попадают и карты, которые НИКОГДА не
    разбирались (у них флаг false с рождения, миграция 048). Такой
    downgrade отнял бы право у людей, которые им ещё не пользовались, —
    то есть навредил бы сильнее, чем сам откат должен был исправить.

    Заводить колонку-отметку ради обратимости разовой правки тоже не стоит:
    она осталась бы в схеме навсегда ради события, которое случается один
    раз.

    Если откат всё же понадобится — восстанавливать из бэкапа
    (pg_dump снимается ежедневно, см. CLAUDE.md), а не этой функцией.
    """
    pass
