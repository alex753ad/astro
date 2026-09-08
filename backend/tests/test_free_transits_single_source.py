"""Горизонт транзитов free — один источник истины, сам тарифный флаг.

До 08.09.2026 их было два: `TIER_FLAGS["free"]["transits_months"]` стоял
нулём, а фактический горизонт (3 месяца) держала отдельная константа
`FREE_TRANSITS_TEASER_MONTHS` мимо флага. Мотив был в том, чтобы не смешивать
«что человек видит» и «за что платит», но смешения и не было: за AI-разбор
отвечают `transits_ai` / `transits_ai_per_month`, а флаг длины списка описывал
длину списка.

Цена второго источника была не теоретической. `get_feature_flags` производит
из того же флага булев признак `features.transits` — и отдавал клиенту
`false` при живой витрине на 3 месяца. Фронтенд знал, что это неправда, и
обходил флаг руками (`ProfilePage.jsx`: `ok: isFreeTier ? true :
!!feat.transits`), иначе в профиле было написано «транзитов нет» ровно там,
где в таймлайне они есть.

⚠️ Что эти тесты защищают, помимо самого равенства: наблюдаемая граница free
после правки НЕ изменилась. Подъём флага 0 → 3 — перенос уже существующего
числа на его законное место, а не расширение доступа. Если следующая правка
сетки этот горизонт подвинет, упадёт test_free_window_is_unchanged, и это
будет верно — двигать витрину free можно только решением владельца.
"""

from datetime import date
from types import SimpleNamespace

import pytest

import backend.auth.rate_limits as rl
from backend.auth.rate_limits import (
    TIER_FLAGS,
    get_feature_flags,
    transits_date_window,
    transits_horizon_months,
)


class TestSingleSource:
    def test_horizon_comes_from_the_flag(self):
        """Падал до правки: горизонт был 3, флаг — 0."""
        assert transits_horizon_months("free") == TIER_FLAGS["free"]["transits_months"]

    def test_flag_is_not_zero(self):
        """Ноль вернул бы прежнюю ложь и заодно снёс бы витрину free.

        Под блюром должно быть что показать: FreePlanBanner со счётчиком
        закрытых транзитов и PlanComparisonModal строятся на этих данных.
        """
        assert TIER_FLAGS["free"]["transits_months"] > 0

    def test_no_second_constant_in_the_module(self):
        """Падал до правки: константа существовала.

        Проверка именно на отсутствие имени, а не на совпадение значений:
        два числа, обязанные совпадать, — та самая конструкция, которая в
        этом проекте уже расходилась (charts_per_month против
        profiles_limit, копии тарифной сетки).
        """
        assert not hasattr(rl, "FREE_TRANSITS_TEASER_MONTHS")


class TestDerivedFeatureFlag:
    @pytest.mark.parametrize("tier", ["free", "lite", "pro", "premium"])
    def test_transits_is_true_for_every_tier(self, tier):
        """Падал до правки на free: сервер отдавал transits = false.

        Список транзитов открыт всем тарифам (решение E2) — значит признак
        обязан быть истинным везде, иначе клиенту приходится его обходить.
        """
        user = SimpleNamespace(tier=tier, free_interpretation_used=False)
        assert get_feature_flags(user)["transits"] is True

    def test_ai_flags_did_not_move(self):
        """Подъём флага НЕ открыл free платного: AI-разбор остался закрыт."""
        user = SimpleNamespace(tier="free", free_interpretation_used=False)
        flags = get_feature_flags(user)
        assert flags["transits_ai"] is False
        assert flags["transits_ai_limited"] is False
        assert TIER_FLAGS["free"]["transits_ai_per_month"] == 0


class TestObservableWindowUnchanged:
    @pytest.mark.parametrize("today,expected_end", [
        (date(2026, 8, 15), date(2026, 11, 30)),
        (date(2026, 12, 15), date(2027, 3, 31)),
        (date(2024, 1, 15), date(2024, 4, 30)),
    ])
    def test_free_window_is_unchanged(self, today, expected_end):
        """Те же границы, что отдавала константа до правки."""
        assert transits_date_window("free", today)[1] == expected_end

    def test_free_still_does_not_outrun_a_paid_tier(self):
        free_months = TIER_FLAGS["free"]["transits_months"]
        for tier in ("lite", "pro", "premium"):
            assert TIER_FLAGS[tier]["transits_months"] >= free_months
