"""Лента событий: единое время, устойчивые ключи, настоящие даты периодов.

Три обязательных проверки задания плюс регрессии на файлы, которые лента
переиспользует и потому вынужденно правила.

Тесты идут по build_feed напрямую, а не через HTTP: проверяется форма данных,
а не доступ, а расчёт эфемерид достаточно дорогой, чтобы не гонять его через
клиента лишний раз.
"""

from __future__ import annotations

import types
from datetime import date, datetime

import pytest

from backend.auth.rate_limits import transits_date_window
from backend.feed.builder import build_feed, feed_cache, transit_text
from backend.feed.horizon import feed_horizon


# Натальная карта с фиксированными долготами. Настоящие числа не нужны —
# движку транзитов важны только долготы натальных точек, — но они обязаны быть
# постоянными: тест на устойчивость ключей иначе проверял бы генератор
# случайных чисел.
_NATAL_PLANETS = [
    {"name": "Sun",        "longitude": 84.3,  "sign": "Gemini"},
    {"name": "Moon",       "longitude": 344.6, "sign": "Pisces"},
    {"name": "Mercury",    "longitude": 65.6,  "sign": "Gemini"},
    {"name": "Venus",      "longitude": 47.2,  "sign": "Taurus"},
    {"name": "Mars",       "longitude": 12.9,  "sign": "Aries"},
    {"name": "Jupiter",    "longitude": 106.8, "sign": "Cancer"},
    {"name": "Saturn",     "longitude": 291.4, "sign": "Capricorn"},
    {"name": "Uranus",     "longitude": 277.1, "sign": "Capricorn"},
    {"name": "Neptune",    "longitude": 283.5, "sign": "Capricorn"},
    {"name": "Pluto",      "longitude": 225.2, "sign": "Scorpio"},
    {"name": "North Node", "longitude": 310.0, "sign": "Aquarius"},
    {"name": "South Node", "longitude": 130.0, "sign": "Leo"},
]

# Ключи именно `number`/`degree`: _extract_cusps (house_passages.py) читает
# только их, а на чужой форме молча отдаёт двенадцать нулей — и тогда планер
# возвращает пустые списки, а тесты про периоды проверяют пустоту.
_HOUSES = [
    {"number": i + 1, "degree": (185.7 + i * 30) % 360, "sign": "—"} for i in range(12)
]


def _chart(time_unknown: bool = False):
    return types.SimpleNamespace(
        id="feed-test-chart",
        planets=_NATAL_PLANETS,
        houses=_HOUSES,
        ascendant={"longitude": 200.0, "sign": "Libra"},
        midheaven={"longitude": 110.0, "sign": "Cancer"},
        timezone="Europe/Moscow",
        time_unknown=time_unknown,
    )


@pytest.fixture(autouse=True)
def _clear_feed_cache():
    """Кэш чанков — модульный синглтон, живущий между тестами.

    Без очистки тест на устойчивость ключей стал бы бессмысленным: второе и
    третье окно читали бы готовый чанк и совпали бы с первым независимо от
    того, детерминирован расчёт или нет.
    """
    feed_cache.clear()
    yield
    feed_cache.clear()


def _feed(from_d: date, to_d: date, tier: str = "pro", **kw):
    return build_feed(chart=_chart(**kw), from_date=from_d, to_date=to_d,
                      today=date(2026, 9, 4), tier=tier)


# ═══════════════════════════════════════════════════════════
# 1. Устойчивость ключей
# ═══════════════════════════════════════════════════════════

class TestKeysAreWindowIndependent:
    """Один и тот же транзит из разных окон — один ключ.

    Это главное требование к ленте, и оно не даётся даром: сырой
    calculate_transits ищет пик ВНУТРИ переданного диапазона, и у окна, куда
    настоящий пик не попал, возвращает край окна. Проверено боем на трёх
    перекрывающихся окнах: peak_date разошёлся у 4 транзитов из 31,
    peak_orb — у тех же четырёх (FEED_API_RECON_2026-09-04.md).

    Лента лечит это месячной сеткой — см. шапку builder.py.
    """

    def test_same_transit_same_key_from_three_windows(self):
        w1 = _feed(date(2026, 9, 1), date(2026, 9, 30))
        feed_cache.clear()
        w2 = _feed(date(2026, 9, 10), date(2026, 10, 10))
        feed_cache.clear()
        w3 = _feed(date(2026, 8, 20), date(2026, 9, 25))

        def transits(f):
            return {
                (e["meta"]["transit_planet"], e["meta"]["natal_planet"],
                 e["meta"]["aspect_type"], e["at"]): e["key"]
                for e in f["events"] if e["kind"] == "transit"
            }

        t1, t2, t3 = transits(w1), transits(w2), transits(w3)
        common = set(t1) & set(t2) & set(t3)
        assert common, "окна не пересеклись — тест ничего не проверяет"

        for ident in common:
            assert t1[ident] == t2[ident] == t3[ident], (
                f"ключ транзита {ident} разъехался между окнами"
            )

    def test_same_transit_same_moment_from_three_windows(self):
        """Не только ключ, но и сам момент на оси не должен плыть.

        Ключ мог бы совпасть и при разных датах, если бы в него не входила
        дата пика. Здесь проверяется именно то, из-за чего ключи и ломались:
        peak_date как таковой.
        """
        def moments(f):
            """Тройка → множество моментов.

            Именно множество, а не одно значение: одна и та же тройка
            (планета, натальная точка, аспект) за окно встречается несколько
            раз — ретроградная планета проходит аспект по три раза. Свернув её
            в одно значение, тест сравнивал бы разные проходы между собой и
            падал бы на верном коде.
            """
            out: dict[tuple, set] = {}
            for e in f["events"]:
                if e["kind"] == "transit":
                    ident = (e["meta"]["transit_planet"], e["meta"]["natal_planet"],
                             e["meta"]["aspect_type"])
                    out.setdefault(ident, set()).add(e["at"])
            return out

        m1 = moments(_feed(date(2026, 9, 1), date(2026, 9, 30)))
        feed_cache.clear()
        m2 = moments(_feed(date(2026, 8, 15), date(2026, 10, 15)))

        common = set(m1) & set(m2)
        assert common
        # Широкое окно видит больше проходов, поэтому сравниваем пересечение:
        # момент, известный обоим окнам, обязан совпадать. Момент, который
        # видно только широкому окну, — это проход в августе или октябре, и
        # узкому сентябрьскому окну его знать неоткуда.
        for ident in common:
            shared = m1[ident] & m2[ident]
            assert shared or not (m1[ident] & m2[ident]), ident
            for moment in m1[ident]:
                if moment in m2[ident]:
                    continue
                # Момент из сентябрьского окна обязан быть и в широком —
                # широкое включает сентябрь целиком.
                assert False, (
                    f"момент {moment} транзита {ident} есть в узком окне, "
                    f"но не в широком: {sorted(m2[ident])}"
                )

    def test_chunks_add_up_without_duplicates(self):
        """Месяц + месяц = то же, что оба месяца одним запросом.

        Событие принадлежит ровно одному месячному чанку — иначе на стыке
        окон транзит двоился бы, а лента показывала бы его дважды.
        """
        aug = _feed(date(2026, 8, 1), date(2026, 8, 31))
        feed_cache.clear()
        sep = _feed(date(2026, 9, 1), date(2026, 9, 30))
        feed_cache.clear()
        both = _feed(date(2026, 8, 1), date(2026, 9, 30))

        def keys(f):
            return [e["key"] for e in f["events"] if e["kind"] == "transit"]

        assert len(keys(both)) == len(set(keys(both))), "дубли транзитов в одном ответе"
        assert set(keys(aug)) | set(keys(sep)) == set(keys(both))


# ═══════════════════════════════════════════════════════════
# 2. Единое время
# ═══════════════════════════════════════════════════════════

class TestSingleTimezone:
    """До ленты форматов времени было шесть, и затмения приходили в UTC,
    когда фазы Луны — в GMT+3 (находка 3.7 CLAUDE.md, подтверждена боем)."""

    def test_every_event_has_explicit_offset(self):
        feed = _feed(date(2026, 8, 1), date(2026, 8, 31))
        assert feed["events"]
        for e in feed["events"]:
            parsed = datetime.fromisoformat(e["at"])
            assert parsed.tzinfo is not None, f"{e['kind']} без зоны: {e['at']}"
            if e["ends_at"]:
                assert datetime.fromisoformat(e["ends_at"]).tzinfo is not None

    def test_all_events_in_chart_timezone(self):
        """Зона одна на всю ленту — и это ИМЕННО зона, а не смещение.

        Сравнивать utcoffset нельзя: у долгосрочных периодов начало уезжает на
        годы назад (Плутон в разведке шёл с 2012 года), а Москва до 2014-го
        жила на UTC+4. Разные смещения у событий одной ленты — правильное
        поведение pytz, а не расхождение поясов.
        """
        feed = _feed(date(2026, 8, 1), date(2026, 8, 31))
        assert feed["timezone"] == "Europe/Moscow"
        for e in feed["events"]:
            tzname = datetime.fromisoformat(e["at"]).tzname()
            assert tzname is not None
            # Москва: MSK круглый год, перевода времени нет с 2014-го.
            assert tzname.startswith("MSK") or "+0" in tzname, (
                f"{e['kind']} в чужой зоне: {e['at']} ({tzname})"
            )

    def test_events_sorted_by_time(self):
        """Лента отсортирована по моменту — с одной оговоркой (D+B, см.
        CLAUDE.md «planner_longterm»): событие, начавшееся раньше окна
        (долгий планер), встаёт по max(at, начало окна), а не по своему
        настоящему `at` — иначе Плутон с 2012 года стоял бы первым в любой
        ленте. Сортировка по clamp'нутому моменту и есть то, что проверяется
        здесь; сырой `at` при этом не меняется — см. TestLongtermSortAndStartedBefore.
        """
        feed = _feed(date(2026, 8, 1), date(2026, 8, 31))
        clamped = [max(e["at"], feed["from_date"]) for e in feed["events"]]
        assert clamped == sorted(clamped)

    def test_eclipse_and_phase_share_the_zone(self):
        """Август 2026 — месяц с двумя затмениями. Оба совпадают по моменту
        со своей фазой (проверено исполнением, FEED_DUPLICATE_MOMENTS.md —
        7 затмений из 7 боевых сопровождались фазой того же рода) и поэтому
        обе фазы месяца слиты в затмения (см. TestEclipseAbsorbsPhase) — тем
        не менее их момент по-прежнему взят из общего jd_to_utc, той же
        функции, что и раньше отдавала разные пояса для затмений (UTC) и
        фаз (GMT+3). Сверяем зону на затмении и на любом другом лунном виде
        того же месяца (retrograde/solar_event/planner), которые дедупу не
        подлежат.
        """
        feed = _feed(date(2026, 8, 1), date(2026, 8, 31))
        kinds = {e["kind"] for e in feed["events"]}
        assert "eclipse" in kinds, "в августе 2026 два затмения — их нет в ленте"
        zones = {
            datetime.fromisoformat(e["at"]).utcoffset()
            for e in feed["events"] if e["kind"] in ("eclipse", "retrograde", "solar_event")
        }
        assert len(zones) == 1, f"разные пояса внутри одной ленты: {zones}"


# ═══════════════════════════════════════════════════════════
# Дубль затмения и фазы — вариант Б (решение владельца 05.09.2026)
# ═══════════════════════════════════════════════════════════

class TestEclipseAbsorbsPhase:
    """Затмение — это фаза: солнечное бывает только в новолуние, лунное —
    только в полнолуние. Показывать оба — значит показать один момент
    дважды. Решение: фаза, совпавшая с затмением по времени (не по дате —
    см. ниже), не отдаётся; её знак зодиака переезжает в meta затмения.

    Август 2026 — боевой месяц с двумя затмениями: полное солнечное 12.08
    (совпадает с новолунием) и частное лунное 28.08 (совпадает с
    полнолунием). Оба подтверждены исполнением на бою
    (FEED_DUPLICATE_MOMENTS.md).
    """

    def test_both_august_phases_are_absorbed(self):
        feed = _feed(date(2026, 8, 1), date(2026, 8, 31))
        kinds = {e["kind"] for e in feed["events"]}
        assert "eclipse" in kinds
        assert "moon_phase" not in kinds, (
            "в августе 2026 обе фазы месяца совпадают со своими затмениями — "
            "ни одна не должна остаться отдельным событием"
        )

    def test_eclipse_carries_the_sign_the_phase_would_have_shown(self):
        """У затмения своего знака в данных нет (`get_eclipses` его не
        считает) — без переноса содержание терялось бы вместе с фазой."""
        feed = _feed(date(2026, 8, 1), date(2026, 8, 31))
        eclipses = [e for e in feed["events"] if e["kind"] == "eclipse"]
        assert len(eclipses) == 2
        for e in eclipses:
            assert e["meta"].get("sign"), f"у затмения {e['at']} нет знака: {e['meta']}"

    def test_eclipse_key_and_text_unchanged_by_the_merge(self):
        """Ключи существующих событий не меняются (условие задания) —
        только состав ленты (фаза пропадает) и meta затмения (знак
        добавляется)."""
        feed = _feed(date(2026, 8, 1), date(2026, 8, 31))
        eclipses = {e["key"]: e for e in feed["events"] if e["kind"] == "eclipse"}
        assert any("Полное солнечное" in e["text"] for e in eclipses.values())
        assert any("Частное лунное" in e["text"] for e in eclipses.values())

    def test_threshold_is_hours_not_calendar_date(self):
        """Порог сверки — реальное время, а не строка даты. Синтетическая
        фаза и затмение на РАЗНЫХ календарных днях (23:50 / 00:05), но в
        пределах 3 часов, обязаны слиться — иначе пара, разошедшаяся через
        полночь по местному времени (наблюдалось на бою: до 19 минут вокруг
        полуночи), осталась бы дублем."""
        import pytz
        from backend.feed.builder import _lunar_events

        tz = pytz.timezone("Europe/Moscow")
        # Патчим _find_phase и _scan_eclipses прямо на модуле lunar_engine —
        # _lunar_events импортирует их внутри функции (см. её тело), поэтому
        # патч на месте импорта, откуда их читают, а не на месте вызова.
        import backend.calendar.lunar_engine as engine

        new_moon_jd = engine._jd(date(2026, 6, 15), 23.0) + 50 / 1440   # 23:50 UTC
        eclipse_jd = new_moon_jd + 15 / 1440                            # +15 минут → 00:05 UTC следующих суток

        orig_find_phase = engine._find_phase
        orig_scan = engine._scan_eclipses

        def fake_find_phase(jd_start, jd_end, target):
            return [new_moon_jd] if target == 0.0 else []

        def fake_scan(jd_start, jd_end, finder, flags, etype):
            from backend.calendar.lunar_engine import EclipseEvent
            if etype != "solar":
                return []
            dt, tm = engine._jd_to_dt(eclipse_jd)
            return [EclipseEvent(date=dt, time=f"{tm} UTC", type="solar", kind="total")]

        engine._find_phase = fake_find_phase
        engine._scan_eclipses = fake_scan
        try:
            events = _lunar_events(date(2026, 6, 14), date(2026, 6, 16), tz)
        finally:
            engine._find_phase = orig_find_phase
            engine._scan_eclipses = orig_scan

        kinds = [e["kind"] for e in events]
        assert kinds.count("eclipse") == 1
        assert kinds.count("moon_phase") == 0, (
            f"фаза и затмение на разных календарных днях не слились: "
            f"{[(e['kind'], e['at']) for e in events]}"
        )


# ═══════════════════════════════════════════════════════════
# 3. Год у периодов через границу декабря
# ═══════════════════════════════════════════════════════════

class TestPlannerPeriodsHaveRealDates:
    """Планер отдаёт границы строкой «07.08 — 06.09» — без года.

    Год приходилось доставать из заголовка месяца парсером; на периоде через
    31 декабря такой разбор даёт две даты одного года вместо двух соседних.
    Лента берёт даты из datetime, поэтому проверяем именно стык года.
    """

    def test_period_crossing_december_keeps_both_years(self):
        feed = _feed(date(2026, 12, 20), date(2027, 1, 20))
        periods = [e for e in feed["events"] if e["kind"] == "planner_period"]
        assert periods, "в окне нет периодов планера — проверять нечего"

        crossing = [
            e for e in periods
            if datetime.fromisoformat(e["at"]).year != datetime.fromisoformat(e["ends_at"]).year
        ]
        assert crossing, "ни один период не пересёк границу года — окно выбрано неудачно"

        for e in crossing:
            start = datetime.fromisoformat(e["at"])
            end = datetime.fromisoformat(e["ends_at"])
            assert end > start
            # Конец НЕ обязан лежать в январе: период быстрой планеты идёт
            # неделями (Марс в этом окне — с 12 декабря по 6 февраля), а
            # долгосрочный — годами. Проверяется ровно то, ради чего тест
            # написан: год конца больше года начала, а не равен ему, как
            # получилось бы при разборе строки «12.12 — 06.02» без года.
            assert end.year > start.year
            assert start.month == 12

        # Отдельно — самый показательный случай: месячная секция, начавшаяся в
        # декабре и кончающаяся в следующем году. Именно её строковый формат
        # «дд.мм — дд.мм» описать не может в принципе.
        month_crossing = [e for e in crossing if e["kind"] == "planner_period"]
        assert month_crossing, "нужен хотя бы один месячный период через границу года"

    def test_periods_are_iso_not_display_strings(self):
        feed = _feed(date(2026, 9, 1), date(2026, 9, 30))
        for e in feed["events"]:
            if e["kind"].startswith("planner"):
                # Разбор не должен требовать знания формата «дд.мм»
                datetime.fromisoformat(e["at"])
                datetime.fromisoformat(e["ends_at"])

    def test_duration_days_present_for_periods(self):
        """Владельцу нужен признак «период длиннее месяца» для отрисовки."""
        feed = _feed(date(2026, 9, 1), date(2026, 9, 30))
        longterm = [e for e in feed["events"] if e["kind"] == "planner_longterm"]
        assert longterm
        for e in longterm:
            assert isinstance(e["duration_days"], int)
            assert e["duration_days"] > 0
        assert any(e["duration_days"] > 31 for e in longterm), (
            "долгосрочные транзиты идут месяцами — хотя бы один обязан быть длиннее месяца"
        )

    def test_transits_carry_no_period(self):
        """start_date/end_date у транзита обрезаются окном без пометки,
        поэтому в ленту не отдаются вовсе (решение владельца)."""
        feed = _feed(date(2026, 9, 1), date(2026, 9, 30))
        for e in feed["events"]:
            if e["kind"] == "transit":
                assert e["ends_at"] is None
                assert e["duration_days"] is None
                assert "start_date" not in e["meta"]
                assert "end_date" not in e["meta"]


# ═══════════════════════════════════════════════════════════
# planner_longterm: сортировка по max(at, окно), started_before, at честный
# ═══════════════════════════════════════════════════════════

class TestLongtermSortAndStartedBefore:
    """Медленная планета выбирается по «содержит сегодня», а не по попаданию
    начала периода в окно (house_passages.py) — значит planner_longterm может
    начаться на много лет раньше запроса. До правки такое событие сортировалось
    по настоящему `at` и улетало в начало ленты, за «месяц назад» (см. CLAUDE.md,
    «planner_longterm», разбор от 05.09.2026). Правка не трогает ни `at`, ни
    ключ — только позицию в сортировке и новый флаг `started_before`.
    """

    def test_at_stays_real_not_clamped_to_window(self):
        """`at` долгого периода — настоящая дата начала, а не первый день окна."""
        feed = _feed(date(2026, 9, 1), date(2026, 9, 30))
        longterm = [e for e in feed["events"] if e["kind"] == "planner_longterm"]
        before = [e for e in longterm if e["at"] < feed["from_date"]]
        assert before, "нет периода, начавшегося раньше окна, — тест ничего не проверяет"
        for e in before:
            assert e["at"][:10] != feed["from_date"], (
                "at обрезан по окну — должен остаться настоящим началом периода"
            )

    def test_started_before_matches_at_vs_window(self):
        """Флаг обязан совпадать с прямым сравнением at и начала окна ответа —
        ни для одного события они не должны разойтись, независимо от kind."""
        feed = _feed(date(2026, 9, 1), date(2026, 9, 30))
        for e in feed["events"]:
            assert e["started_before"] == (e["at"] < feed["from_date"]), e["key"]

    def test_started_before_true_for_long_pluto_period(self):
        """Показательный случай: самый долгий период (Плутон) обязан быть
        started_before=True, а обычные события окна — False."""
        feed = _feed(date(2026, 9, 1), date(2026, 9, 30))
        longterm = [e for e in feed["events"] if e["kind"] == "planner_longterm"]
        assert longterm
        longest = max(longterm, key=lambda e: e["duration_days"])
        assert longest["started_before"] is True

        within_window = [e for e in feed["events"] if e["at"] >= feed["from_date"]]
        assert within_window
        assert all(e["started_before"] is False for e in within_window)

    def test_sort_key_is_clamped_not_raw_at(self):
        """Прямая проверка того, что реально изменилось: позиция в ленте
        считается по max(at, from_date), а не по голому at. Ключ сортировки
        наружу не уходит, поэтому проверяем его так же, как его вычисляет
        сам build_feed — тем же выражением на тех же данных."""
        feed = _feed(date(2026, 9, 1), date(2026, 9, 30))
        events = feed["events"]
        assert events
        sort_keys = [max(e["at"], feed["from_date"]) for e in events]
        assert sort_keys == sorted(sort_keys), (
            "лента не отсортирована по max(at, from_date) — старое поведение "
            "(сортировка по голому at) вернуло бы событие 2012 года первым, "
            "но не обязательно в этом порядке относительно окна"
        )

    def test_started_before_group_is_ordered_by_real_at_not_by_key_hash(self):
        """Внутри группы started_before (все клэмпнуты к одному значению)
        вторичный ключ сортировки — настоящий `at`, а не хеш `key`: порядок
        обязан быть хронологическим, а не порядком хеша. До правки на этой
        же фикстуре порядок был Нептун/Уран/Плутон/Сатурн — по хешу key,
        без связи с реальными датами."""
        feed = _feed(date(2026, 9, 1), date(2026, 9, 30))
        events = feed["events"]
        before = [e for e in events if e["started_before"]]
        assert len(before) >= 4, "нужно хотя бы 4 started_before-события для проверки порядка"

        # Хронологический порядок — общее свойство, не привязанное к
        # конкретным датам конкретной (синтетической) карты: реальные даты
        # зависят от куспидов, у тестовой фикстуры они не совпадают с боевой
        # картой из задания (там порядок буквально был Плутон-2012 →
        # Нептун-2018 → Сатурн-04.2026 → Уран-04.2026 — это подтверждено
        # отдельно, боем, а не здесь).
        ats = [e["at"] for e in before]
        assert ats == sorted(ats), f"группа started_before не отсортирована по at: {ats}"

        # И группа обязана идти единым блоком в начале ленты — до любого
        # события, не отмеченного started_before.
        first_not_before = next(i for i, e in enumerate(events) if not e["started_before"])
        assert all(events[i]["started_before"] for i in range(first_not_before)), (
            "started_before-события не образуют сплошной блок в начале ленты"
        )

    def test_transit_keys_still_stable_across_windows_after_sort_change(self):
        """Регресс вчерашней проверки: правка сортировки/started_before —
        отдельный шаг после того, как события уже собраны и получили ключ,
        поэтому устойчивость ключей транзитов (TestKeysAreWindowIndependent)
        обязана остаться в силе и после неё."""
        w1 = _feed(date(2026, 8, 15), date(2026, 10, 15))
        feed_cache.clear()
        w2 = _feed(date(2026, 9, 1), date(2026, 11, 1))

        def transit_keys(f):
            return {
                (e["meta"]["transit_planet"], e["meta"]["natal_planet"],
                 e["meta"]["aspect_type"], e["at"]): e["key"]
                for e in f["events"] if e["kind"] == "transit"
            }

        t1, t2 = transit_keys(w1), transit_keys(w2)
        common = set(t1) & set(t2)
        assert common, "окна не пересеклись — тест ничего не проверяет"
        for ident in common:
            assert t1[ident] == t2[ident], f"ключ транзита {ident} разъехался между окнами"

    @pytest.mark.xfail(
        reason=(
            "Известный пре-существующий дефект (не создан и не в объёме этой "
            "правки, см. CLAUDE.md «planner_longterm»): _key() хеширует сырые "
            "start_iso/end_iso ДО обрезки микросекунд, которую _to_local_iso "
            "делает только для отображаемых at/ends_at. Окна со сдвигом, не "
            "кратным 3 суткам (step_hours=72 в calculate_house_passages), "
            "сдвигают сетку коарсного скана — бисекция сходится к тому же "
            "часу:минуте:секунде, но к другой микросекунде, и ключ расходится, "
            "хотя at/ends_at совпадают дословно. Подтверждено исполнением на "
            "main ДО этой правки — тот же результат, дефект не в сортировке."
        ),
        strict=True,
    )
    def test_longterm_key_stable_across_windows_offset_by_17_days(self):
        """17 дней — сдвиг НЕ кратен 3 (step_hours=72): именно на нём дефект
        и был найден. Тест должен упасть (xfail) — если однажды пройдёт,
        strict=True превратит это в XPASS-провал, и будет сигнал снять xfail
        и обновить CLAUDE.md."""
        w1 = _feed(date(2026, 8, 15), date(2026, 10, 15))
        feed_cache.clear()
        w2 = _feed(date(2026, 9, 1), date(2026, 11, 1))

        def longterm_by_planet(f):
            return {
                e["meta"]["planet"]: e["key"]
                for e in f["events"] if e["kind"] == "planner_longterm"
            }

        l1, l2 = longterm_by_planet(w1), longterm_by_planet(w2)
        common = set(l1) & set(l2)
        assert common, "окна не пересеклись по planner_longterm — тест ничего не проверяет"
        for planet in common:
            assert l1[planet] == l2[planet], f"ключ planner_longterm ({planet}) разъехался между окнами"


# ═══════════════════════════════════════════════════════════
# Шкала важности
# ═══════════════════════════════════════════════════════════

class TestImportance:

    def test_three_levels_only(self):
        feed = _feed(date(2026, 8, 1), date(2026, 8, 31))
        assert {e["importance"] for e in feed["events"]} <= {"high", "medium", "low"}

    def test_moon_transits_are_low(self):
        feed = _feed(date(2026, 8, 1), date(2026, 8, 31))
        moon = [e for e in feed["events"]
                if e["kind"] == "transit" and e["meta"]["transit_planet"] == "Moon"]
        assert moon, "лунных транзитов не может не быть — их три четверти ленты"
        assert all(e["importance"] == "low" for e in moon)

    def test_significant_transits_and_eclipses_are_high(self):
        feed = _feed(date(2026, 8, 1), date(2026, 8, 31))
        for e in feed["events"]:
            if e["kind"] == "transit" and e["meta"]["significant"]:
                # Луна значимой быть не может (значимость = медленная планета
                # к личной точке), поэтому конфликта уровней здесь нет.
                assert e["importance"] == "high"
            if e["kind"] == "eclipse":
                assert e["importance"] == "high"

    def test_phases_and_planner_are_medium(self):
        feed = _feed(date(2026, 8, 1), date(2026, 8, 31))
        for e in feed["events"]:
            if e["kind"] in ("moon_phase", "planner_period", "planner_longterm",
                             "planner_moon_house", "solar_event", "retrograde"):
                assert e["importance"] == "medium"


# ═══════════════════════════════════════════════════════════
# Тарифы и шаблоны
# ═══════════════════════════════════════════════════════════

class TestTierAndTemplates:

    def test_locked_periods_keep_their_frame(self):
        """Закрытый период отдаёт каркас: даты, дом, планету — под размытый блок."""
        feed = _feed(date(2026, 9, 1), date(2026, 9, 30), tier="free")
        locked = [e for e in feed["events"] if e["locked"]]
        assert locked, "на free часть периодов обязана быть закрыта"
        for e in locked:
            assert e["at"] and e["ends_at"]
            assert e["meta"]["house"]
            assert e["meta"]["planet"]
            assert e["meta"]["theme"] == ""
            assert e["meta"]["groups"] == []

    def test_pro_sees_more_than_free(self):
        free = _feed(date(2026, 9, 1), date(2026, 9, 30), tier="free")
        pro = _feed(date(2026, 9, 1), date(2026, 9, 30), tier="pro")
        n_free = sum(1 for e in free["events"] if e["locked"])
        n_pro = sum(1 for e in pro["events"] if e["locked"])
        assert n_pro < n_free

    def test_transit_title_matches_the_web(self):
        """Заголовок собирается ровно как строка `key` в LockedTransitPanel.

        Веб уже показывает бесплатному пользователю «Уран Соединение
        Меркурий» (TransitTimeline.jsx, PLANET_LABELS_RU + ASPECT_LABELS_RU).
        Лента обязана показывать ту же подпись, иначе в приложении на месте
        текста будет пусто там, где на сайте текст есть.
        """
        assert transit_text("Uranus", "Mercury", "conjunction") == "Уран Соединение Меркурий"
        assert transit_text("Jupiter", "Mars", "trine") == "Юпитер Трин Марс"

    def test_every_transit_has_a_title(self):
        """Ни одного транзита без подписи — иначе в ленте пустой значок."""
        feed = _feed(date(2026, 8, 1), date(2026, 8, 31), tier="free")
        transits = [e for e in feed["events"] if e["kind"] == "transit"]
        assert transits
        missing = [e["meta"] for e in transits if not e["text"]]
        assert not missing, f"транзиты без подписи: {missing[:3]}"

    def test_free_gets_the_same_teaser_as_the_web(self):
        """Бесплатному вместо разбора — та же подводка, что на ChartPage."""
        feed = _feed(date(2026, 8, 1), date(2026, 8, 31), tier="free")
        teasers = [e["teaser"] for e in feed["events"]
                   if e["kind"] == "transit" and e["teaser"]]
        assert teasers, "на free подводка обязана быть"
        assert teasers[0]["intro"].startswith("Это активный период по одной из ключевых тем")
        assert "Веге" in teasers[0]["outro"]

    def test_paid_tiers_get_no_teaser(self):
        """Подводка — замена разбора. Тем, кому разбор открыт, она не нужна."""
        feed = _feed(date(2026, 8, 1), date(2026, 8, 31), tier="pro")
        assert all(e["teaser"] is None for e in feed["events"])

    def test_free_unlocked_transits_get_no_teaser(self):
        """Топ-2 значимых на free — разбор открыт, подводка не нужна.

        Условие взято с фронта (isEventVisible в TransitTimeline.jsx).
        """
        feed = _feed(date(2026, 8, 1), date(2026, 8, 31), tier="free")
        unlocked = [e for e in feed["events"]
                    if e["kind"] == "transit" and e["meta"]["free_unlocked"]]
        assert unlocked, "топ-2 значимых обязаны быть хотя бы в одном месяце"
        assert all(e["teaser"] is None for e in unlocked)

    def test_templates_match_the_web_dictionaries(self):
        """Файл — вторая копия словарей фронта, и она обязана им совпадать.

        Пока веб берёт подписи из своего JSX, а лента из templates.json, это
        два источника одной правды. Тест не сводит их в один (это отдельная
        задача, см. _readme в файле), но ловит расхождение.
        """
        from backend.feed.builder import TEMPLATES

        web_aspects = {
            "conjunction": "Соединение", "sextile": "Секстиль", "square": "Квадрат",
            "trine": "Трин", "opposition": "Оппозиция",
        }
        web_planets = {
            "Sun": "Солнце", "Moon": "Луна", "Mercury": "Меркурий", "Venus": "Венера",
            "Mars": "Марс", "Jupiter": "Юпитер", "Saturn": "Сатурн", "Uranus": "Уран",
            "Neptune": "Нептун", "Pluto": "Плутон", "North Node": "Сев. Узел",
        }
        assert TEMPLATES["aspects"] == web_aspects
        for eng, ru in web_planets.items():
            assert TEMPLATES["natal_labels"][eng] == ru, eng
        # Юж. Узел приходит как натальная точка, но в словаре веба его нет
        # вовсе — там подпись просто не отрисуется. В ленте она есть.
        assert TEMPLATES["natal_labels"]["South Node"] == "Юж. Узел"

    def test_templates_cover_every_combination_(self):
        """Каркас обязан покрывать все комбинации, иначе часть транзитов
        останется без подписи навсегда, и это не будет видно."""
        from backend.ephemeris.calculator import PLANETS
        from backend.feed.builder import TEMPLATES
        from backend.transit.engine import TRANSIT_ORBS

        transit_planets = set(PLANETS) - {"North Node"}
        assert transit_planets <= set(TEMPLATES["transit_planets"])
        assert set(TRANSIT_ORBS) == set(TEMPLATES["aspects"])
        # Узлы приходят как натальные точки, но в PLANET_NAMES_RU их нет —
        # именно поэтому метки живут в templates.json, а не берутся оттуда.
        for point in list(PLANETS) + ["South Node"]:
            assert point in TEMPLATES["natal_labels"], f"нет метки для {point}"


class TestTeaserTextSingleSource:
    """intro/outro тизера дублируют текст LockedTransitPanel(reason="free")
    с веба (TransitTimeline.jsx) — два файла разных рантаймов (JS-компонент,
    Python+JSON), синхронизированных только человеческой памятью
    (FEED_TEASER_TEXT_RECON.md). Веб-путь боевой, трогать его ради общего
    источника рискованно — вместо этого тест-склейка по образцу
    TestOfferDocumentsTheRule (test_subscription_renewal.py): читает оба
    файла как текст и ловит расхождение здесь, а не в проде через полгода.

    Проверяется не вхождение (`in`), а единственность (`count == 1`) — иначе
    тест прошёл бы и в случае, когда текст-совпадение — случайность
    (например, слово входит частью в более длинную соседнюю строку), и не
    заметил бы, если строку продублировали ещё где-то на вебе. Плюс —
    что найденный литерал стоит именно в ветке `reason === "free"` (после
    `:` тернарника), а не по ошибке в ветке `lite-limit` (после `?`).
    """

    @staticmethod
    def _jsx() -> str:
        from pathlib import Path
        return Path(__file__).resolve().parents[2].joinpath(
            "frontend", "src", "components", "TransitTimeline.jsx"
        ).read_text(encoding="utf-8")

    def test_intro_and_outro_appear_exactly_once_in_the_web_component(self):
        from backend.feed.builder import TEMPLATES

        jsx = self._jsx()
        intro = TEMPLATES["teaser"]["free"]["intro"]
        outro = TEMPLATES["teaser"]["free"]["outro"]

        assert jsx.count(intro) == 1, (
            "intro не встречается в TransitTimeline.jsx ровно один раз — "
            "либо разошлись, либо текст продублирован на вебе"
        )
        assert jsx.count(outro) == 1, (
            "outro не встречается в TransitTimeline.jsx ровно один раз — "
            "либо разошлись, либо текст продублирован на вебе"
        )

    def test_literal_sits_in_the_free_branch_not_lite_limit(self):
        """Оба литерала — правая (false) часть тернарника `reason ===
        "lite-limit" ? ... : "ТЕКСТ"`. Правая часть в JS всегда следует сразу
        за `:` — если бы литерал оказался в левой (`?`) части, перед ним
        стоял бы `?`, а не `:`."""
        from backend.feed.builder import TEMPLATES

        jsx = self._jsx()
        for field in ("intro", "outro"):
            text = TEMPLATES["teaser"]["free"][field]
            idx = jsx.index(f'"{text}"')
            before = jsx[:idx].rstrip()
            assert before.endswith(":"), (
                f"{field}: перед литералом в JSX нет `:` — похоже, текст "
                f"стоит в ветке lite-limit (после `?`), а не free (после `:`)"
            )


# ═══════════════════════════════════════════════════════════
# Прочее
# ═══════════════════════════════════════════════════════════

class TestHorizon:
    """Границы ленты: месяц назад всем, вперёд по тарифу, край не пустой.

    Решение владельца 04.09.2026.
    """

    def test_past_is_one_month_for_every_tier(self):
        today = date(2026, 9, 4)
        for tier in ("free", "lite", "pro", "premium"):
            h = feed_horizon(tier, today)
            assert h.start == date(2026, 8, 4), (
                f"{tier}: прошлое обязано быть одинаковым для всех тарифов"
            )

    def test_future_grows_with_tier(self):
        today = date(2026, 9, 4)
        ends = [feed_horizon(t, today).end for t in ("free", "lite", "pro", "premium")]
        assert ends == sorted(ends), ends
        assert len(set(ends)) > 1, "горизонты тарифов не должны совпадать все разом"

    def test_future_comes_from_transits_window(self):
        """Своей арифметики горизонта у ленты нет — только transits_date_window."""
        today = date(2026, 9, 4)
        for tier in ("free", "lite", "pro", "premium"):
            assert feed_horizon(tier, today).end == transits_date_window(tier, today)[1]

    def test_next_tier_is_reported_with_its_date(self):
        """Фронту нужно, чем подписать край: дата и следующий тариф."""
        h = feed_horizon("free", date(2026, 9, 4)).to_dict()
        assert h["next_tier"]["tier"] == "lite"
        assert h["next_tier"]["name"] == "Вега"
        assert h["next_tier"]["to"] > h["to"], "на следующем тарифе край обязан быть дальше"

    def test_top_tier_has_no_next(self):
        assert feed_horizon("premium", date(2026, 9, 4)).to_dict()["next_tier"] is None

    def test_window_is_clamped_not_rejected(self):
        """Запрос за край — не ошибка, а обрезка с границей в ответе."""
        feed = _feed(date(2026, 8, 1), date(2027, 6, 30), tier="free")
        assert feed["to_date"] == feed["horizon"]["to"]
        assert feed["from_date"] == feed["horizon"]["from"]

    def test_lunar_events_do_not_leak_past_the_horizon(self):
        """ОБЯЗАТЕЛЬНЫЙ тест задания.

        /calendar/lunar тарифного гейта не имеет вовсе — публичная ручка,
        отдаёт любой месяц без авторизации. Если лента не обрежет её своим
        горизонтом, за краем транзитов останутся одинокие затмения и фазы, и
        это будет выглядеть поломкой, а не границей тарифа.
        """
        today = date(2026, 9, 4)
        end = feed_horizon("free", today).end
        # Март 2027 — заведомо за горизонтом free (тот кончается 31.12.2026),
        # и в нём есть лунные события: они приходят в любой месяц.
        assert date(2027, 3, 1) > end

        feed = _feed(date(2027, 3, 1), date(2027, 3, 31), tier="free")
        assert feed["events"] == [], "за горизонтом не должно быть ни одного события"
        lunar = [e for e in feed["events"] if e["kind"] in ("moon_phase", "eclipse", "solar_event")]
        assert not lunar

    def test_edge_response_still_carries_the_border(self):
        """Пустая лента за краем всё равно объясняет, где край и что дальше."""
        feed = _feed(date(2027, 3, 1), date(2027, 3, 31), tier="free")
        assert feed["events"] == []
        assert feed["horizon"]["to"] == "2026-12-31"
        assert feed["horizon"]["next_tier"]["name"] == "Вега"

    def test_planner_obeys_the_same_horizon(self):
        """Планер не может уехать дальше транзитов."""
        feed = _feed(date(2026, 8, 1), date(2027, 6, 30), tier="free")
        edge = feed["horizon"]["to"]
        for e in feed["events"]:
            if e["kind"].startswith("planner"):
                # Начало периода может лежать в прошлом (долгосрочные идут
                # годами) — проверяется, что лента не показала период,
                # НАЧАВШИЙСЯ за краем.
                assert e["at"][:10] <= edge, (e["kind"], e["at"])

    def test_past_edge_cuts_events_too(self):
        feed = _feed(date(2026, 1, 1), date(2026, 9, 30), tier="pro")
        assert feed["from_date"] == feed["horizon"]["from"]
        transits = [e for e in feed["events"] if e["kind"] == "transit"]
        assert transits
        assert min(e["at"][:10] for e in transits) >= feed["horizon"]["from"]


class TestFeedShape:

    def test_moon_phases_not_duplicated(self):
        """_find_phase ловит смену знака дважды за оборот — в самой фазе и на
        противоположной точке орбиты. Без отсечения на каждое новолуние
        приходило фантомное полнолуние через восемь часов: за сентябрь 2026
        получалось четыре фазы вместо двух."""
        feed = _feed(date(2026, 9, 1), date(2026, 9, 30))
        phases = [e for e in feed["events"] if e["kind"] == "moon_phase"]
        assert len(phases) == 2, [(e["at"], e["text"]) for e in phases]
        assert {e["meta"]["type"] for e in phases} == {"new_moon", "full_moon"}

    def test_no_planner_without_birth_time(self):
        """Без времени рождения домов нет — планер выпадает, остальное живо."""
        feed = _feed(date(2026, 9, 1), date(2026, 9, 30), time_unknown=True)
        kinds = {e["kind"] for e in feed["events"]}
        assert not any(k.startswith("planner") for k in kinds)
        assert "transit" in kinds
        assert "moon_phase" in kinds

    def test_daily_signs_not_in_feed(self):
        """Фон дня, а не событие — решение владельца 04.09.2026."""
        feed = _feed(date(2026, 9, 1), date(2026, 9, 30))
        assert all(e["kind"] != "daily_sign" for e in feed["events"])

    def test_keys_are_unique_within_response(self):
        feed = _feed(date(2026, 8, 1), date(2026, 9, 30))
        keys = [e["key"] for e in feed["events"]]
        assert len(keys) == len(set(keys))
