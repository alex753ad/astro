"""Блок «Лунные фазы недели» в еженедельном дайджесте.

Два дефекта одного блока, найденные 04.09.2026.

1. `p.to_dict()["title"]` — поля `title` у CalendarEvent нет вовсе. KeyError
   глотал общий except, и блок не показывался НИ РАЗУ с момента написания.

2. Фазы брались только за текущий календарный месяц, а неделя дайджеста
   пересекает границу месяца. Фаза первых чисел следующего месяца молча
   терялась.

Тест повторяет выборку письма, а не зовёт send_weekly_digest целиком: тот
требует пользователя, карту, транзиты и Resend, и проверял бы всё что угодно,
кроме этих двух строк.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from backend.calendar.lunar_engine import get_moon_phases


def _week_phases(now: date) -> list:
    """Фазы недели ровно так, как их набирает письмо (email_service.py)."""
    week_end = now + timedelta(days=7)
    months = dict.fromkeys([(now.year, now.month), (week_end.year, week_end.month)])
    phases = []
    for year, month in months:
        phases += get_moon_phases(year, month)
    return [
        p for p in phases
        if now <= date.fromisoformat(p.to_dict()["date"]) <= week_end
    ]


class TestFieldsExist:
    """Первый дефект: обращение к несуществующему ключу."""

    def test_calendar_event_has_no_title_field(self):
        """Именно отсутствие `title` и роняло блок — фиксируем факт, чтобы
        правка не откатилась «обратно к title» при следующем чтении."""
        p = get_moon_phases(2026, 9)[0]
        assert "title" not in p.to_dict()

    def test_fields_used_by_the_email_are_present(self):
        for p in get_moon_phases(2026, 9):
            d = p.to_dict()
            assert d["date"] and d["description"] and d["emoji"]

    def test_rendered_line_is_not_empty(self):
        """Строка письма собирается и содержит дату, значок и описание."""
        p = get_moon_phases(2026, 9)[0].to_dict()
        line = f'{p["date"]} — {p["emoji"]} {p["description"]}'
        assert line.startswith("2026-09-")
        assert "Новолуние" in line or "Полнолуние" in line


class TestMonthBoundary:
    """Второй дефект: неделя через границу месяца теряла фазу.

    Даты не выдуманы — это ровно те две недели, которые нашлись прогоном по
    году вперёд от сентября 2026.
    """

    @pytest.mark.parametrize("monday,expected", [
        (date(2027, 6, 29), "2027-07-04"),
        (date(2027, 7, 27), "2027-08-02"),
    ])
    def test_phase_in_next_month_is_included(self, monday, expected):
        dates = [p.to_dict()["date"] for p in _week_phases(monday)]
        assert expected in dates, (
            f"фаза {expected} потеряна: неделя с {monday} задевает следующий месяц"
        )

    def test_no_phase_is_lost_over_a_year(self):
        """Ни одна фаза года не должна пропасть из-за границы месяца."""
        cache: dict = {}

        def phases(year, month):
            if (year, month) not in cache:
                cache[(year, month)] = get_moon_phases(year, month)
            return cache[(year, month)]

        day = date(2026, 9, 1)
        while day < date(2027, 9, 1):
            week_end = day + timedelta(days=7)
            shown = {p.to_dict()["date"] for p in _week_phases(day)}
            real = set()
            for year, month in {(day.year, day.month), (week_end.year, week_end.month)}:
                real |= {
                    p.to_dict()["date"] for p in phases(year, month)
                    if day <= date.fromisoformat(p.to_dict()["date"]) <= week_end
                }
            assert real == shown, f"неделя с {day}: потеряно {sorted(real - shown)}"
            day += timedelta(days=7)

    def test_no_duplicates_when_week_stays_inside_one_month(self):
        """Оба «месяца» совпадают — фазы не должны задвоиться."""
        dates = [p.to_dict()["date"] for p in _week_phases(date(2026, 9, 7))]
        assert len(dates) == len(set(dates))
