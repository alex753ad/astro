"""Блок «Лунные фазы недели» в еженедельном дайджесте (week_phase_lines).

История: до 04.09.2026 блок не показывался ни разу (KeyError глотал except),
неделя через границу месяца теряла фазу; до 04.10.2026 дата была UTC.
Теперь фазы — lunations_local, дата — местная (шаг 6 аудита).
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from backend.email_service import week_phase_lines


@pytest.mark.parametrize("monday,expected", [
    (date(2027, 6, 29), "2027-07-04"),
    (date(2027, 7, 27), "2027-08-02"),
])
def test_phase_in_next_month_is_included(monday, expected):
    lines = week_phase_lines(monday, monday + timedelta(days=7), "Europe/Moscow")
    assert any(x.startswith(expected) for x in lines)


def test_line_format():
    lines = week_phase_lines(date(2026, 10, 5), date(2026, 10, 12), "Europe/Moscow")
    assert lines == ["2026-10-10 — 🌑 Новолуние в Весах"]


def test_local_date_vladivostok():
    """Новолуние 10.10.2026 18:50 МСК — во Владивостоке 11.10 01:50."""
    lines = week_phase_lines(date(2026, 10, 5), date(2026, 10, 12), "Asia/Vladivostok")
    assert lines == ["2026-10-11 — 🌑 Новолуние в Весах"]
