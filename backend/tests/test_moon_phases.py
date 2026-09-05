"""Фазы Луны: ровно две в месяц (кроме подтверждённой «чёрной луны»), без
фантомов и без потерь на границе окна.

Два независимых дефекта одной функции, `_find_phase`, найдены в разные дни.

1) Регрессия дефекта от 04.09.2026: `_find_phase` ловит смену знака разности
углов Луна−Солнце, а знак меняется дважды за оборот — в самой фазе и на
противоположной точке орбиты. Второе — не фаза, но бисекция сходилась к
границе шага и возвращала момент с круглым временем. Итог до правки:
`get_moon_phases` отдавала ЧЕТЫРЕ фазы в месяц вместо двух — на каждое
новолуние фантомное полнолуние в тот же день и наоборот.

Кто это видел: пуши (`push/cron.py`) — пользователю с включёнными лунными
уведомлениями 10 сентября 2026 уходило два уведомления разом, «Новолуние
завтра» и «Полнолуние завтра», а 27-го ещё одно, про несуществующее
новолуние. `/calendar/lunar` не показывал: там свой цикл со своей проверкой.

2) Регрессия дефекта от 05.09.2026: `while jd < jd_end` никогда не вычисляет
угол ровно в `jd_end`, поэтому фаза в последних 12 часах окна не находится ни
текущим месяцем, ни следующим (тот сканирует вперёд от `jd_end`, назад не
заглядывает). За 2026–2035 теряются 5 фаз, см. `TestPhaseAtMonthBoundary`.

⚠️ Побочный эффект правки №2, не дефект: она же впервые честно показала, что
август 2027 — настоящая «чёрная луна», ДВА новолуния в одном календарном
месяце (02.08 и 31.08). Подтверждено независимым расчётом `/calendar/lunar`
(`_compute_lunar_calendar`, `main.py`) — оба движка согласны. Раньше второе
новолуние пряталось той же самой ошибкой, что теряла фазы на границе окна, и
`test_two_phases_per_month` был написан по данным, где эта ошибка ещё не
чинилась — отсюда его прежнее допущение «ровно две фазы всегда».
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from backend.calendar.lunar_engine import _find_phase, _jd, get_moon_phases


# Пятнадцать месяцев подряд через границу года. Одного месяца мало: дефект
# воспроизводился в каждом, но проверка на одном не поймала бы, например,
# декабрь, где окно сканирования уходит в следующий год.
_MONTHS = [(2026, m) for m in range(9, 13)] + [(2027, m) for m in range(1, 12)]


# Единственный подтверждённый случай «чёрной луны» в проверяемом промежутке:
# два новолуния в августе 2027 (02.08 и 31.08). Сверено независимым расчётом
# (_compute_lunar_calendar, main.py) — оба движка согласны, это не дефект.
# Без этой записи test_two_phases_per_month падал бы на (2027, 8) и выглядел
# бы как регресс дефекта №1, хотя причина ровно обратная: до правки №2
# второе новолуние в этом месяце не находилось вовсе.
_BLACK_MOON_MONTHS = {(2027, 8): ["full_moon", "new_moon", "new_moon"]}


class TestExactlyTwoPhasesPerMonth:

    @pytest.mark.parametrize("year,month", _MONTHS)
    def test_two_phases_per_month(self, year, month):
        """В календарном месяце ровно одно новолуние и одно полнолуние —
        кроме документированной «чёрной луны» (`_BLACK_MOON_MONTHS`).

        Лунный месяц ~29.5 суток, поэтому в 30-31-дневном месяце пара фаз
        каждого типа теоретически возможна («голубая луна» для полнолуний,
        «чёрная луна» для новолуний). Один такой месяц в проверяемом
        промежутке есть, и это не находка теста, а известный факт.
        """
        phases = get_moon_phases(year, month)
        types = sorted(p.type for p in phases)
        expected = _BLACK_MOON_MONTHS.get((year, month), ["full_moon", "new_moon"])
        assert types == expected, (
            f"{year}-{month:02d}: ожидались {expected}, пришло {len(phases)}: "
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


class TestPhaseAtMonthBoundary:
    """Регрессия дефекта от 05.09.2026: `while jd < jd_end` никогда не
    вычисляет угол ровно в `jd_end`, поэтому фаза в последних 12 часах
    месяца терялась — не находилась ни этим месяцем, ни следующим (его
    сканирование начинается ровно с этой границы и назад не заглядывает).

    Все пять дат ниже — полный список потерь за 2026–2035, найден сверкой с
    независимым расчётом (не выборка, а весь горизонт, на который заведён
    поиск).
    """

    _LOST = [
        (2027, 8, "2027-08-31", "new_moon"),
        (2028, 12, "2028-12-31", "full_moon"),
        (2029, 2, "2029-02-28", "full_moon"),
        (2030, 6, "2030-06-30", "new_moon"),
        (2031, 9, "2031-09-30", "full_moon"),
    ]

    @pytest.mark.parametrize("year,month,expected_date,expected_type", _LOST)
    def test_lost_phase_now_found(self, year, month, expected_date, expected_type):
        phases = get_moon_phases(year, month)
        match = [p for p in phases if p.date == expected_date and p.type == expected_type]
        assert match, (
            f"{expected_date} {expected_type} не найдена в get_moon_phases({year}, {month}): "
            f"{[(p.date, p.type) for p in phases]}"
        )

    @pytest.mark.parametrize("year,month,expected_date,expected_type", _LOST)
    def test_lost_phase_not_duplicated_in_next_month(self, year, month, expected_date, expected_type):
        """Расширение окна на полшага вперёд не должно давать ту же фазу
        дважды — один раз текущим месяцем (правильно), второй раз соседним
        (эта же дата чужим месяцем — дубль)."""
        next_year, next_month = (year + 1, 1) if month == 12 else (year, month + 1)
        next_phases = get_moon_phases(next_year, next_month)
        leaked = [p for p in next_phases if p.date == expected_date]
        assert not leaked, (
            f"{expected_date} утекла в get_moon_phases({next_year}, {next_month}): {leaked}"
        )

    @pytest.mark.parametrize("year,month,expected_date,expected_type", _LOST)
    def test_current_and_next_month_together_have_no_duplicate_dates(
        self, year, month, expected_date, expected_type,
    ):
        """То же самое, но по всему месяцу, а не только по потерянной дате:
        два соседних месяца в сумме не должны давать повторяющуюся фазу ни
        по одной дате — расширение окна затрагивает весь хвост месяца, не
        только точку, на которой поймали дефект."""
        next_year, next_month = (year + 1, 1) if month == 12 else (year, month + 1)
        current = [(p.date, p.type) for p in get_moon_phases(year, month)]
        nxt = [(p.date, p.type) for p in get_moon_phases(next_year, next_month)]
        combined = current + nxt
        assert len(combined) == len(set(combined)), (
            f"дубли между {year}-{month:02d} и {next_year}-{next_month:02d}: {combined}"
        )

    def test_bisection_result_never_exceeds_jd_end_even_off_grid(self):
        """Явный отсев `found > jd_end`, а не только докстринг-обещание, что
        вызывающие передают границы, кратные шагу (05.09.2026, вторым
        заходом). Оба текущих вызывающих (get_moon_phases, _lunar_events)
        этот путь никогда не задевают — их границы всегда полночь-в-полночь.
        Синтетические вызовы ниже намеренно берут jd_end НЕ кратным шагу
        (0.5 суток) вокруг известного новолуния 12.08.2026 17:36 UTC — без
        отсева расширенный скан `jd_end + step` дотягивался бы до него из-за
        границы, всё равно превышающей jd_end, и молча отдавал бы момент
        за пределами запрошенного окна.
        """
        jd_start = _jd(date(2026, 8, 1), 0)

        # jd_end раньше истинного новолуния (17:36) — расширенный скан
        # дотягивается до него (следующая точка сетки — 13.08 00:00, она
        # дальше и 15:00, и +step от 15:00), бисекция сходится к ~17:36,
        # но это позже jd_end=15:00 — без отсева утекло бы наружу.
        jd_end_before = _jd(date(2026, 8, 12), 15.0)
        found_before = _find_phase(jd_start, jd_end_before, target=0)
        assert found_before == [], (
            f"момент за пределами jd_end={jd_end_before} не отсеян: {found_before}"
        )

        # jd_end чуть позже истинного новолуния — оно законно внутри окна и
        # обязано найтись как обычно; отсев не должен резать легитимные
        # результаты за компанию.
        jd_end_after = _jd(date(2026, 8, 12), 18.0)
        found_after = _find_phase(jd_start, jd_end_after, target=0)
        assert found_after, "новолуние 12.08.2026 не найдено — отсев режет лишнее"
        assert all(jd <= jd_end_after for jd in found_after)

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
