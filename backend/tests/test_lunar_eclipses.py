"""Затмения из /calendar/lunar приходят в GMT+3, как фазы и равноденствия.

До 14.09.2026 get_eclipses отдавала UTC — единственный вид событий этой
ручки, уезжавший в чужом поясе. Фронт метку "UTC" молча срезал и подписывал
результат GMT+3, а у события около полуночи вместе со временем уезжала ДАТА:
значок вставал в соседнюю клетку месяца (находка 3.7 в CLAUDE.md).

⚠️ Даты в тестах настоящие, не выдуманные: это реальные затмения, у которых
UTC-момент приходится на последние часы суток. Проверять пересчёт на событии
в середине дня бессмысленно — там смена пояса даты не меняет, и тест был бы
зелёным на несдвинутом коде.
"""

from datetime import date

from backend.calendar.lunar_engine import get_eclipses

# (месяц запроса, дата и время в UTC, дата и время в GMT+3, тип, вид)
NEAR_MIDNIGHT = [
    ((2027, 2),  "2027-02-20", "23:12", "2027-02-21", "02:12", "lunar", "penumbral"),
    ((2029, 12), "2029-12-20", "22:42", "2029-12-21", "01:42", "lunar", "total"),
    ((2030, 12), "2030-12-09", "22:27", "2030-12-10", "01:27", "lunar", "penumbral"),
]


class TestEclipseTimezone:
    def test_near_midnight_eclipse_lands_on_the_local_day(self):
        for (y, m), _utc_d, _utc_t, loc_d, loc_t, etype, kind in NEAR_MIDNIGHT:
            last = 31 if m == 12 else 28
            found = [e for e in get_eclipses(date(y, m, 1), date(y, m, last))
                     if e["type"] == etype and e["kind"] == kind]
            assert found, f"затмение {loc_d} не найдено в выдаче за {y}-{m:02d}"
            e = found[0]
            assert e["date"] == loc_d, f"дата {e['date']}, ожидалась {loc_d} (GMT+3)"
            assert e["time"] == f"{loc_t} GMT+3", f"время {e['time']!r}"

    def test_no_utc_label_anywhere(self):
        """Метка пояса обязана быть одна на всю ручку.

        Фронт (fmtPhaseTime) срезает и "UTC", и "GMT+3" одинаково, поэтому
        расхождение поясов он не показывает — оно видно только по дате.
        Проверяем саму метку, чтобы следующая правка не вернула UTC молча.
        """
        events = get_eclipses(date(2026, 1, 1), date(2026, 12, 31))
        assert events, "в 2026 году затмения есть"
        assert all(e["time"].endswith(" GMT+3") for e in events)
        assert not any("UTC" in e["time"] for e in events)

    def test_scanner_still_speaks_utc(self):
        """_scan_eclipses НЕ переведён на GMT+3 — и это инвариант, а не недосмотр.

        Им пользуется лента (feed/builder.py): она разбирает его строку и
        штампует результат как UTC, а рядом склеивает затмение с фазой по
        порогу ровно в 3 часа. Сдвиг зоны в сканере дал бы ленте время GMT+3
        под ярлыком UTC и вернул бы дубли одного момента.
        """
        import swisseph as swe

        from backend.calendar.lunar_engine import (
            _LUNAR_KIND_FLAGS,
            _jd,
            _scan_eclipses,
        )

        events = _scan_eclipses(_jd(date(2027, 2, 1), 0), _jd(date(2027, 2, 28), 24),
                                swe.lun_eclipse_when, _LUNAR_KIND_FLAGS, "lunar")
        assert events, "лунное затмение 20.02.2027 сканер обязан находить"
        e = events[0]
        assert e.date == "2027-02-20" and e.time == "23:12 UTC"
        assert e.jd > 0, "момент обязан доезжать числом — из него считается GMT+3"
