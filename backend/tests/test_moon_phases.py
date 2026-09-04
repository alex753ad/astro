"""Фазы Луны: ровно две в месяц, без фантомов.

Регрессия дефекта, найденного 04.09.2026. `_find_phase` ловит смену знака
разности углов Луна−Солнце, а знак меняется дважды за оборот: в самой фазе и
на противоположной точке орбиты. Второе — не фаза, но бисекция сходилась к
границе шага и возвращала момент с круглым временем.

Итог до правки: `get_moon_phases` отдавала ЧЕТЫРЕ фазы в месяц вместо двух —
на каждое новолуние фантомное полнолуние в тот же день и наоборот.

Кто это видел: пуши (`push/cron.py`) — пользователю с включёнными лунными
уведомлениями 10 сентября 2026 уходило два уведомления разом, «Новолуние
завтра» и «Полнолуние завтра», а 27-го ещё одно, про несуществующее
новолуние. `/calendar/lunar` не показывал: там свой цикл со своей проверкой.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from backend.calendar.lunar_engine import get_moon_phases


# Пятнадцать месяцев подряд через границу года. Одного месяца мало: дефект
# воспроизводился в каждом, но проверка на одном не поймала бы, например,
# декабрь, где окно сканирования уходит в следующий год.
_MONTHS = [(2026, m) for m in range(9, 13)] + [(2027, m) for m in range(1, 12)]


class TestExactlyTwoPhasesPerMonth:

    @pytest.mark.parametrize("year,month", _MONTHS)
    def test_two_phases_per_month(self, year, month):
        """В календарном месяце ровно одно новолуние и одно полнолуние.

        Лунный месяц ~29.5 суток, поэтому в 30-31-дневном месяце пара фаз
        каждого типа теоретически возможна (это и есть «голубая луна»), но
        для проверяемого промежутка её нет ни в одном месяце — сверено с
        боевым /calendar/lunar, который считает фазы независимо.
        """
        phases = get_moon_phases(year, month)
        types = sorted(p.type for p in phases)
        assert types == ["full_moon", "new_moon"], (
            f"{year}-{month:02d}: ожидались две фазы, пришло {len(phases)}: "
            f"{[(p.date, p.time, p.type) for p in phases]}"
        )

    @pytest.mark.parametrize("year,month", _MONTHS)
    def test_phases_belong_to_the_month(self, year, month):
        for p in get_moon_phases(year, month):
            assert p.date.startswith(f"{year:04d}-{month:02d}-"), p

    def test_december_crosses_into_next_year(self):
        """Декабрь сканирует до 1 января следующего года — граница года не
        должна ни терять настоящую фазу, ни впускать фантомную."""
        phases = get_moon_phases(2026, 12)
        assert sorted(p.type for p in phases) == ["full_moon", "new_moon"]

    def test_no_phantom_round_times(self):
        """Фантом узнавался по круглому времени: бисекция сходилась к границе
        шага сканирования и давала ровно 00:00 или 12:00 UTC.

        Настоящая фаза попадает на круглую минуту с вероятностью примерно
        1/1440, поэтому массовое совпадение — признак возвращения дефекта.
        """
        round_times = []
        for year, month in _MONTHS:
            for p in get_moon_phases(year, month):
                if p.time in ("00:00 UTC", "12:00 UTC"):
                    round_times.append((year, month, p.date, p.time, p.type))
        assert not round_times, f"похоже на фантомы: {round_times}"


class TestAgainstIndependentCalculation:
    """Сверка со вторым, независимым расчётом фаз в main.py.

    /calendar/lunar считает фазы своим циклом и своей проверкой — он дефекта
    не имел. Значит это готовый эталон: два независимых пути обязаны давать
    одни и те же моменты.
    """

    @pytest.mark.parametrize("year,month", [(2026, 9), (2026, 12), (2027, 1)])
    def test_matches_calendar_lunar(self, year, month):
        from backend.main import _compute_lunar_calendar

        engine = {(p.date, p.type) for p in get_moon_phases(year, month)}
        # _compute_lunar_calendar отдаёт даты в GMT+3, get_moon_phases — в UTC,
        # поэтому сравниваются типы и порядок, а не сами даты: у фазы около
        # полуночи они законно расходятся на сутки.
        lunar = [(p["date"], p["type"]) for p in _compute_lunar_calendar(year, month)["phases"]]
        assert len(engine) == len(lunar), (
            f"{year}-{month:02d}: движок дал {len(engine)}, /calendar/lunar — {len(lunar)}"
        )
        assert sorted(t for _, t in engine) == sorted(t for _, t in lunar)


class TestPushNotifications:
    """Пуши — единственная поверхность, где фантомы видел пользователь.

    Проверяется не текст уведомления, а то, что попадает в кандидаты:
    push/cron.py фильтрует фазы по `phase.date == завтра` и на каждую
    подходящую кладёт один пуш.
    """

    def _pushes_for(self, day: date) -> list[str]:
        """Какие лунные пуши ушли бы накануне `day` — та же выборка, что в
        push/cron.py: фазы месяца, у которых дата совпадает с завтрашним днём."""
        return [
            p.type for p in get_moon_phases(day.year, day.month)
            if p.date == day.isoformat()
        ]

    def test_one_push_on_the_real_new_moon(self):
        """10 сентября 2026 уходило ДВА пуша: настоящее новолуние 11-го и
        фантомное полнолуние того же дня. Должен остаться один."""
        assert self._pushes_for(date(2026, 9, 11)) == ["new_moon"]

    def test_one_push_on_the_real_full_moon(self):
        assert self._pushes_for(date(2026, 9, 26)) == ["full_moon"]

    def test_no_push_on_the_phantom_day(self):
        """27 сентября 2026 уходил пуш про новолуние, которого не существует."""
        assert self._pushes_for(date(2026, 9, 27)) == []

    def test_no_push_on_an_ordinary_day(self):
        assert self._pushes_for(date(2026, 9, 15)) == []

    def test_at_most_one_push_per_day_over_a_year(self):
        """Двух лунных пушей в один день не бывает: новолуние и полнолуние
        разделены примерно двумя неделями."""
        day = date(2026, 9, 1)
        while day < date(2027, 9, 1):
            pushes = self._pushes_for(day)
            assert len(pushes) <= 1, f"{day}: {pushes}"
            day += timedelta(days=1)
