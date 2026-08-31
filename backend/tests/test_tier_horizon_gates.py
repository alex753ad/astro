"""Серверные тарифные гейты горизонта: транзиты и планер.

До 31.08.2026 обоих не существовало. `transits_months` и `planner_months`
жили в TIER_FLAGS, но на бэкенде не читались нигде: горизонт держался
исключительно на арифметике фронтенда, и прямой запрос мимо интерфейса
отдавал Веге транзиты на 24 месяца и планер на год вперёд.
`check_transit_access` была написана и не вызывалась ни разу.

Ключевое требование к этим проверкам: они ставятся ПОД уже существующее
поведение, а не вместо него. Поэтому граница считается так же, как её
считает `TransitTimeline.jsx` (конец месяца `today + horizon`, текущий месяц
входит целиком → листается `horizon + 1` месяцев), а прошлое ограничено
общим бэкстопом, а не тарифом — кнопка «‹» и в таймлайне, и в планере
отматывает назад без нижней границы на всех тарифах.
"""

from datetime import date, timedelta

import pytest

from backend.auth.rate_limits import (
    FREE_TRANSITS_TEASER_MONTHS,
    PAST_WINDOW_ABUSE_MONTHS,
    TIER_FLAGS,
    planner_offset_window,
    transits_date_window,
    transits_horizon_months,
)


@pytest.fixture
def created_chart_pro(client, mock_calculator, mock_geo, auth_headers_pro):
    """Карта, принадлежащая Pro-пользователю.

    `created_chart` из conftest.py привязана к user_free, а BOLA-защита
    (resolve_chart_access) отдаёт 404 на чужую карту независимо от тарифа —
    для проверки Pro-границы нужна своя. Дублирует фикстуру из
    test_forecast_limits.py: она там локальная, а не в conftest.
    """
    resp = client.post(
        "/api/v1/chart/calculate",
        json={
            "birth_date": "1990-01-10",
            "birth_time": "12:00",
            "birth_place": "Moscow",
            "house_system": "placidus",
        },
        headers=auth_headers_pro,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


# ═══════════════════════════════════════════════════════════
# Горизонт транзитов — арифметика границы
# ═══════════════════════════════════════════════════════════


class TestTransitsWindowArithmetic:
    @pytest.mark.parametrize("tier,expected", [
        ("free", FREE_TRANSITS_TEASER_MONTHS),
        ("lite", 1),
        ("pro", 3),
        ("premium", 24),
    ])
    def test_horizon_per_tier(self, tier, expected):
        assert transits_horizon_months(tier) == expected

    def test_free_horizon_is_not_the_tier_flag(self):
        """Витрина free не выводится из transits_months — там 0.

        Если кто-то «починит» это приравниванием, free перестанет видеть
        список транзитов, а с ним развалится весь апселл на витрине (E2).
        """
        assert TIER_FLAGS["free"]["transits_months"] == 0
        assert transits_horizon_months("free") == FREE_TRANSITS_TEASER_MONTHS > 0

    def test_free_sees_further_than_pro_and_that_is_intended(self):
        """Странность, которую нельзя «исправлять»: free дальше Лиры."""
        assert transits_horizon_months("free") > transits_horizon_months("pro")

    @pytest.mark.parametrize("today,tier,expected_end", [
        # Обычный день месяца: конец месяца today + horizon.
        (date(2026, 8, 15), "lite", date(2026, 9, 30)),
        (date(2026, 8, 15), "pro", date(2026, 11, 30)),
        (date(2026, 8, 15), "premium", date(2028, 8, 31)),
        (date(2026, 8, 15), "free", date(2027, 8, 31)),
        # Конец года — переход через границу лет.
        (date(2026, 12, 15), "lite", date(2027, 1, 31)),
        # Високосный февраль.
        (date(2024, 1, 15), "lite", date(2024, 2, 29)),
    ])
    def test_upper_bound_is_month_end(self, today, tier, expected_end):
        assert transits_date_window(tier, today)[1] == expected_end

    def test_current_month_is_included_so_lite_gets_two_months(self):
        """Вега видит текущий и следующий месяц — так работает интерфейс.

        Это наблюдаемое поведение прода, а не ошибка округления: горизонт
        отсчитывается от КОНЦА текущего месяца. Строгий `today + 1 месяц`
        отобрал бы у платящей Веги месяц, который она видит сегодня.
        """
        _, end = transits_date_window("lite", date(2026, 8, 15))
        assert end == date(2026, 9, 30)

    def test_past_bound_is_flat_not_per_tier(self):
        """Прошлое не монетизируется — бэкстоп один на все тарифы."""
        starts = {transits_date_window(t, date(2026, 8, 15))[0]
                  for t in ("free", "lite", "pro", "premium")}
        assert len(starts) == 1
        assert starts.pop() == date(2024, 8, 1)

    def test_previous_month_is_always_allowed(self):
        """Первый же запрос таймлайна берёт прошлый месяц — на любом тарифе.

        `TransitTimeline.jsx` грузит [today-1мес, today] параллельно с
        forward-запросом. Гейт, начинающийся с сегодня, отдал бы 403 при
        каждом открытии вкладки.
        """
        today = date(2026, 8, 15)
        for tier in ("free", "lite", "pro", "premium"):
            start, _ = transits_date_window(tier, today)
            assert start <= date(2026, 7, 15)

    @pytest.mark.parametrize("today", [
        date(2026, 8, 31), date(2026, 12, 31), date(2026, 1, 31), date(2024, 2, 29),
    ])
    def test_month_boundary_gives_a_day_of_slack(self, today):
        """В ночь смены месяца фронтенд (локальное время) уже в следующем.

        Сервер считает по UTC. Без запаса в сутки Москва получала бы 403 на
        несколько часов каждый месяц. Проверяем, что окно не уже, чем у
        пользователя, для которого уже наступило первое число.
        """
        tomorrow = today + timedelta(days=1)
        server_end = transits_date_window("lite", today)[1]
        client_end = transits_date_window("lite", tomorrow)[1]
        assert server_end >= client_end


# ═══════════════════════════════════════════════════════════
# Горизонт транзитов — сам эндпоинт
# ═══════════════════════════════════════════════════════════


def _transits(client, chart_id, headers, from_d, to_d):
    return client.get(
        f"/api/v1/chart/{chart_id}/transits",
        params={"from_date": from_d.isoformat(), "to_date": to_d.isoformat()},
        headers=headers,
    )


class TestTransitsEndpointGate:
    def test_inside_horizon_passes(self, client, created_chart, auth_headers_free):
        """Free на своей границе — проходит (витрина E2 не тронута)."""
        today = date.today()
        _, end = transits_date_window("free", today)
        resp = _transits(client, created_chart, auth_headers_free, today, end)
        assert resp.status_code != 403, resp.text

    def test_beyond_horizon_is_403(self, client, created_chart, auth_headers_free):
        today = date.today()
        _, end = transits_date_window("free", today)
        resp = _transits(client, created_chart, auth_headers_free,
                         end + timedelta(days=1), end + timedelta(days=2))
        assert resp.status_code == 403
        assert "горизонт" in resp.json()["detail"].lower()

    def test_far_past_is_403(self, client, created_chart, auth_headers_free):
        """Отматывание назад без границы — закрыто бэкстопом."""
        start, _ = transits_date_window("free", date.today())
        resp = _transits(client, created_chart, auth_headers_free,
                         start - timedelta(days=60), start - timedelta(days=30))
        assert resp.status_code == 403

    def test_current_month_still_works(self, client, created_chart, auth_headers_free):
        """То, что видит пользователь сегодня, продолжает работать."""
        today = date.today()
        resp = _transits(client, created_chart, auth_headers_free,
                         today, today + timedelta(days=25))
        assert resp.status_code != 403, resp.text

    def test_previous_month_still_works(self, client, created_chart, auth_headers_free):
        """Первый запрос вкладки «Транзиты» — [today-1мес, today]."""
        today = date.today()
        resp = _transits(client, created_chart, auth_headers_free,
                         today - timedelta(days=30), today)
        assert resp.status_code != 403, resp.text


# ═══════════════════════════════════════════════════════════
# Горизонт планера
# ═══════════════════════════════════════════════════════════


class TestPlannerOffsetWindow:
    @pytest.mark.parametrize("tier,expected_max", [
        ("free", 0), ("lite", 3), ("pro", 12), ("premium", 12),
    ])
    def test_max_offset_is_the_tier_flag(self, tier, expected_max):
        assert planner_offset_window(tier)[1] == expected_max
        assert planner_offset_window(tier)[1] == TIER_FLAGS[tier]["planner_months"]

    def test_ui_reachable_offsets_are_allowed_for_paid(self):
        """Кнопка «›» в PlannerPage доходит до 11 — это обязано проходить."""
        for tier in ("pro", "premium"):
            assert planner_offset_window(tier)[1] >= 11

    def test_past_is_flat_backstop_not_tier(self):
        mins = {planner_offset_window(t)[0] for t in ("free", "lite", "pro", "premium")}
        assert mins == {-PAST_WINDOW_ABUSE_MONTHS}


def _planner(client, chart_id, headers, offset=None):
    params = {} if offset is None else {"month_offset": offset}
    return client.get(
        f"/api/v1/chart/{chart_id}/planner/monthly", params=params, headers=headers
    )


class TestPlannerEndpointGate:
    def test_current_month_works_for_free(self, client, created_chart, auth_headers_free):
        """Free видит планер текущего месяца — интерфейс так и делает."""
        assert _planner(client, created_chart, auth_headers_free).status_code == 200

    def test_free_offset_zero_explicit_works(self, client, created_chart, auth_headers_free):
        assert _planner(client, created_chart, auth_headers_free, 0).status_code == 200

    def test_free_cannot_page_forward(self, client, created_chart, auth_headers_free):
        """Прямой запрос мимо интерфейса — 403. Раньше отдавал планер."""
        resp = _planner(client, created_chart, auth_headers_free, 1)
        assert resp.status_code == 403
        assert "Планер" in resp.json()["detail"]

    def test_free_far_forward_is_403(self, client, created_chart, auth_headers_free):
        assert _planner(client, created_chart, auth_headers_free, 99).status_code == 403

    def test_pro_within_limit_passes(self, client, created_chart_pro, auth_headers_pro):
        assert _planner(client, created_chart_pro, auth_headers_pro, 11).status_code == 200

    def test_pro_beyond_limit_is_403(self, client, created_chart_pro, auth_headers_pro):
        assert _planner(client, created_chart_pro, auth_headers_pro, 13).status_code == 403

    def test_far_past_is_403(self, client, created_chart, auth_headers_free):
        assert _planner(client, created_chart, auth_headers_free, -99).status_code == 403
