"""Миграция 049 возвращает право там, где сохранённого разбора нет.

Карты, разобранные до bab8098, остались в тупике: SSE-путь текст не сохранял,
поэтому natal_charts.free_interpretation_used = true, строки в interpretations
нет, при открытии — отказ, а восстановить нечего.

Тестируется сама функция upgrade() из файла миграции, а не её пересказ:
op.get_bind() подменяется на соединение тестовой сессии. Иначе тест проверял
бы условие, переписанное второй раз, — то есть ровно то, что расходится с
кодом первым.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.models import Interpretation
from backend.tests.test_chart_access import _make_chart

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic" / "versions" / "049_forgive_lost_interpretations.py"
)


def _load_migration():
    """Модуль начинается с цифры — обычным import не берётся."""
    spec = importlib.util.spec_from_file_location("migration_049", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def run_upgrade(db):
    """Прогнать upgrade() миграции на соединении тестовой сессии."""
    module = _load_migration()

    def _run():
        with patch.object(module.op, "get_bind", return_value=db.connection()):
            module.upgrade()
        db.expire_all()

    return _run


def _spent_without_text(db, user):
    """Карта из «до правки»: право потрачено, текста нет."""
    chart = _make_chart(db, user_id=user.id)
    chart.free_interpretation_used = True
    db.commit()
    return chart


def _spent_with_text(db, user):
    """Карта, у которой разбор сохранён, — трогать её нельзя."""
    chart = _make_chart(db, user_id=user.id)
    chart.free_interpretation_used = True
    db.add(Interpretation(
        chart_id=chart.id,
        profile_hash="hash-049",
        engine="deepseek",
        content="Сохранённый разбор.",
        sections=None,
    ))
    db.commit()
    return chart


class TestForgiveness:
    def test_flag_cleared_when_no_text(self, db, user_free, run_upgrade):
        chart = _spent_without_text(db, user_free)

        run_upgrade()

        assert chart.free_interpretation_used is False

    def test_chart_with_text_is_untouched(self, db, user_free, run_upgrade):
        chart = _spent_with_text(db, user_free)

        run_upgrade()

        assert chart.free_interpretation_used is True, (
            "у карты с сохранённым разбором право потрачено по делу"
        )

    def test_both_at_once(self, db, user_free, run_upgrade):
        """Условие различает соседние карты одного пользователя."""
        lost = _spent_without_text(db, user_free)
        kept = _spent_with_text(db, user_free)

        run_upgrade()

        assert lost.free_interpretation_used is False
        assert kept.free_interpretation_used is True

    def test_untouched_chart_stays_untouched(self, db, user_free, run_upgrade):
        """Карта, которую вообще не разбирали, и так с false — миграция
        не должна её как-то задеть."""
        chart = _make_chart(db, user_id=user_free.id)

        run_upgrade()

        assert chart.free_interpretation_used is False


class TestIdempotent:
    def test_second_run_changes_nothing(self, db, user_free, run_upgrade):
        lost = _spent_without_text(db, user_free)
        kept = _spent_with_text(db, user_free)

        run_upgrade()
        run_upgrade()

        assert lost.free_interpretation_used is False
        assert kept.free_interpretation_used is True

    def test_second_run_does_not_revive_the_right(self, db, user_free, run_upgrade):
        """После первого прогона карта уже прощена. Если бы условие было
        написано наоборот, второй прогон вернул бы флаг обратно."""
        lost = _spent_without_text(db, user_free)
        run_upgrade()

        lost.free_interpretation_used = True
        db.commit()
        run_upgrade()

        assert lost.free_interpretation_used is False


class TestUserFlagIsNotTouched:
    def test_users_column_untouched(self, db, user_free, run_upgrade):
        """users.free_interpretation_used — другая колонка: не гейт, но ответ
        на вопрос «разбирал ли пользователь хоть раз». Сбросить её значило бы
        соврать в этом ответе."""
        _spent_without_text(db, user_free)
        user_free.free_interpretation_used = True
        db.commit()

        run_upgrade()

        assert user_free.free_interpretation_used is True
