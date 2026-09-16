"""Недельный горизонт планера: окно ленты и тарифный гейт по проходам Луны.

Задание 16.09.2026. Проверяется ровно то, что до этого дня было сломано молча:

  * лента отдавала ОДНУ неделю на любое окно (4 события на пять месяцев),
    потому что звала функцию, считающую неделю веб-планера;
  * границы прохода приезжали обрезанными по краю окна, то есть с «00:00» —
    моментом, которого не было;
  * время прохода сдвигалось дважды: местное значение ещё раз объявлялось UTC.

Гейт вынесен в отдельный класс без эфемерид — он чистая арифметика недель и
должен проверяться быстро, не расчётом карты.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from backend.feed.builder import MOON_WINDOW_MONTHS_AHEAD, build_feed, feed_cache
from backend.transit.planner_engine import is_moon_week_locked
from backend.tests.test_feed import _chart


# «Сейчас» для всех проверок: пятница 04.09.2026, 15:00.
# Текущая неделя — пн 31.08 … вс 06.09.
NOW = datetime(2026, 9, 4, 15, 0)
TODAY = NOW.date()


@pytest.fixture(autouse=True)
def _clear_feed_cache():
    feed_cache.clear()
    yield
    feed_cache.clear()


def _feed(tier: str = "pro", from_d: date = date(2026, 8, 4), to_d: date = date(2027, 8, 4)):
    return build_feed(chart=_chart(), from_date=from_d, to_date=to_d,
                      today=TODAY, tier=tier, now=NOW)


def _moon(feed) -> list[dict]:
    return [e for e in feed["events"] if e["kind"] == "planner_moon_house"]


# ═══════════════════════════════════════════════════════════
# Гейт: чистая арифметика, без эфемерид
# ═══════════════════════════════════════════════════════════

class TestMoonWeekGate:
    """Правило is_moon_week_locked целиком (решение владельца 16.09.2026)."""

    def _pass(self, start: datetime, days: float = 2.3) -> tuple[str, str]:
        return start.isoformat(), (start + timedelta(days=days)).isoformat()

    @pytest.mark.parametrize("tier", ["free", "lite", "pro", "premium"])
    def test_completed_passage_is_open_to_everyone(self, tier):
        """Завершившийся проход открыт всем — прошлое не продаётся."""
        start, end = self._pass(datetime(2026, 7, 10, 3, 0))
        assert is_moon_week_locked(tier, start, end, NOW) is False

    @pytest.mark.parametrize("tier", ["free", "lite", "pro", "premium"])
    def test_current_week_is_open_to_everyone(self, tier):
        """Текущая неделя открыта на любом тарифе, включая free."""
        start, end = self._pass(datetime(2026, 9, 5, 9, 0))   # сб текущей недели
        assert is_moon_week_locked(tier, start, end, NOW) is False

    def test_free_closes_next_week(self):
        """free — ничего сверх текущей недели."""
        start, end = self._pass(datetime(2026, 9, 7, 9, 0))   # пн следующей
        assert is_moon_week_locked("free", start, end, NOW) is True

    @pytest.mark.parametrize("tier", ["lite", "pro", "premium"])
    def test_paid_has_no_locked_passages_at_all(self, tier):
        """Платный — всё окно, замков нет ни на какой дистанции.

        ⚠️ До 16.09.2026 здесь стояло «четыре недели вперёд, пятая закрыта», и
        это было хуже, чем кажется: у ВСЕХ платных тарифов число было одно и
        то же, то есть закрытую неделю нельзя было открыть ничем — ни временем
        (она не приближалась быстрее), ни деньгами (следующий тариф давал
        столько же). Решение владельца: `planner_weeks_ahead: None`.

        Проверяются три дистанции, включая ту, что за горизонтом самого окна:
        правило не должно зависеть от расстояния вовсе.
        """
        for start in (datetime(2026, 9, 28, 1, 0),      # следующая после прежнего порога
                      datetime(2026, 11, 4, 12, 0),     # через два месяца
                      datetime(2027, 6, 1, 12, 0)):     # через девять
            assert is_moon_week_locked(tier, *self._pass(start), NOW) is False, start

    def test_free_still_closes_the_next_week(self):
        """У free правило не изменилось — иначе платное раздалось бы даром."""
        assert is_moon_week_locked("free", *self._pass(datetime(2026, 9, 7, 9, 0)), NOW) is True
        assert is_moon_week_locked("free", *self._pass(datetime(2026, 11, 4, 12, 0)), NOW) is True

    def test_passage_crossing_the_boundary_belongs_to_its_start(self):
        """Граница проходит ПО ПРОХОДАМ, а не по полуночи воскресенья.

        Проход, начавшийся в субботу последней разрешённой недели и
        кончающийся во вторник следующей, открыт ЦЕЛИКОМ. Иначе один и тот же
        проход был бы одновременно открыт и закрыт.
        """
        start, end = self._pass(datetime(2026, 9, 5, 22, 0), days=3.1)  # сб → вт
        assert end[:10] > "2026-09-06", "проход обязан пересекать границу недели"
        assert is_moon_week_locked("free", start, end, NOW) is False

    def test_without_dates_keeps_the_old_behaviour(self):
        """Вызов без границ остаётся прежним: закрыто на free.

        Ветка нужна тем вызывающим, кому проход неизвестен; убрав её, мы
        получили бы «открыто всем» там, где раньше было «закрыто на free», —
        то есть тихую раздачу платного.
        """
        assert is_moon_week_locked("free") is True
        assert is_moon_week_locked("pro") is False

    def test_unknown_tier_is_treated_as_free(self):
        start, end = self._pass(datetime(2026, 9, 7, 9, 0))
        assert is_moon_week_locked(None, start, end, NOW) is True
        assert is_moon_week_locked("hobbit", start, end, NOW) is True


# ═══════════════════════════════════════════════════════════
# Лента: окно и границы
# ═══════════════════════════════════════════════════════════

class TestMoonPassagesInFeed:

    def test_window_is_covered_not_one_week(self):
        """Проходов примерно окно / 2.3, а не четыре.

        ⚠️ Число «четыре» — это ровно недельная выдача веб-планера, и до
        16.09.2026 лента отдавала именно её на любое окно. Поэтому проверка
        сформулирована через плотность, а не через «больше четырёх»: вторая
        прошла бы и на пяти событиях.
        """
        moon = _moon(_feed())
        assert moon, "проходы Луны обязаны быть в ленте"
        days = (date.fromisoformat(moon[-1]["at"][:10])
                - date.fromisoformat(moon[0]["at"][:10])).days
        assert days > 90, f"окно проходов схлопнулось до {days} дней"
        expected = days / 2.3
        assert expected * 0.8 <= len(moon) <= expected * 1.2, (
            f"{len(moon)} проходов на {days} дней — не похоже на ~2.3 суток на дом"
        )

    def test_window_stops_three_months_ahead_of_this_monday(self):
        """Верхняя граница — три месяца от понедельника текущей недели."""
        moon = _moon(_feed())
        monday = TODAY - timedelta(days=TODAY.weekday())
        assert monday.weekday() == 0
        limit_month = (monday.month - 1 + MOON_WINDOW_MONTHS_AHEAD) % 12 + 1
        last = date.fromisoformat(moon[-1]["at"][:10])
        assert last.month in (limit_month, limit_month - 1), (
            f"последний проход {last} вне окна +{MOON_WINDOW_MONTHS_AHEAD} мес от {monday}"
        )

    @pytest.mark.parametrize("tier", ["free", "lite", "pro", "premium"])
    def test_window_is_the_same_on_every_tier(self, tier):
        """Тариф решает расшифровку, а не наличие события."""
        assert len(_moon(_feed(tier=tier))) == len(_moon(_feed(tier="premium")))

    def test_no_midnight_boundaries_from_clipping(self):
        """Ни одного «00:00» — признак обрезки окном сканирования.

        Луна меняет дом в произвольный момент; ровная полночь на границе
        означала бы, что мы показали край окна вместо настоящего входа.
        Совпасть с полуночью честно она может, но не у полусотни событий
        подряд — поэтому проверка на ноль, а не на долю.
        """
        moon = _moon(_feed())
        bad = [e for e in moon
               if e["at"][11:16] == "00:00" or (e["ends_at"] or "")[11:16] == "00:00"]
        assert not bad, f"обрезанных границ: {len(bad)} из {len(moon)}"

    def test_passages_are_continuous(self):
        """Конец прохода стыкуется с началом следующего.

        Разрыв означал бы потерянный проход, а нахлёст — задвоенный дом.
        Допуск в две минуты: движок закрывает период за минуту до входа в
        следующий дом (calculate_house_passages).
        """
        moon = _moon(_feed())
        for a, b in zip(moon, moon[1:]):
            gap = datetime.fromisoformat(b["at"]) - datetime.fromisoformat(a["ends_at"])
            assert timedelta(0) <= gap <= timedelta(minutes=2), (
                f"{a['ends_at']} → {b['at']}: разрыв {gap}"
            )

    def test_local_time_is_not_shifted_twice(self):
        """Время прохода — местное, а не местное плюс ещё один пояс.

        До 16.09.2026 значение проходило через «наивный UTC → местное» и в
        Москве уезжало на три часа вперёд. Сверяется с тем, что отдаёт сам
        движок домов, — то есть с источником, а не с константой.
        """
        from backend.transit.house_passages import compute_moon_house_passages
        c = _chart()
        raw = compute_moon_house_passages(
            {"planets": c.planets, "houses": c.houses,
             "ascendant": c.ascendant, "midheaven": c.midheaven},
            date(2026, 9, 1), date(2026, 9, 10), "Europe/Moscow",
        )
        assert raw
        moon = {e["at"][:16] for e in _moon(_feed())}
        assert raw[1]["start_dt"][:16] in moon, (
            "время в ленте не совпало с тем, что отдаёт движок домов"
        )

    def test_tier_changes_only_the_payload(self):
        """free видит каркас у закрытого прохода: дом, начало, конец."""
        locked = [e for e in _moon(_feed(tier="free")) if e["locked"]]
        assert locked, "на free часть проходов обязана быть закрыта"
        for e in locked:
            assert e["meta"]["house"]
            assert e["at"] and e["ends_at"]
            assert e["meta"]["theme"] == ""
            assert e["meta"]["groups"] == []

    def test_free_sees_the_past_open(self):
        """Завершившийся проход прошлого месяца открыт даже на free."""
        past = [e for e in _moon(_feed(tier="free")) if e["ends_at"][:19] < NOW.isoformat()]
        assert past, "в окне обязан быть хотя бы один завершившийся проход"
        assert all(not e["locked"] for e in past)
        assert any(e["meta"]["groups"] for e in past), (
            "у открытого прохода обязаны быть рекомендации"
        )

    def test_free_closes_future_and_paid_closes_nothing(self):
        """Сетка работает в ленте: у free закрытое есть, у платного — нет."""
        free_locked = sum(1 for e in _moon(_feed(tier="free")) if e["locked"])
        paid_locked = sum(1 for e in _moon(_feed(tier="pro")) if e["locked"])
        assert free_locked > 0, "у free будущее за текущей неделей обязано быть закрыто"
        assert paid_locked == 0, "у платного замков на проходах Луны не бывает"

    def test_paid_sees_a_passage_two_months_ahead_open(self):
        """Проход через два месяца у платного открыт и с расшифровкой."""
        far = [e for e in _moon(_feed(tier="pro")) if e["at"][:7] >= "2026-11"]
        assert far, "в окне обязан быть проход через два месяца"
        assert all(not e["locked"] for e in far)
        assert any(e["meta"]["groups"] for e in far)


# ═══════════════════════════════════════════════════════════
# Веб-планер не изменился
# ═══════════════════════════════════════════════════════════

class TestWebPlannerUnchanged:
    """`/planner/monthly` c week_offset обязан отдавать ту же неделю."""

    def _planner(self, tier="pro", week_offset=None):
        from backend.transit.planner_engine import build_planner
        c = _chart()
        return build_planner(
            natal_profile={"planets": c.planets, "houses": c.houses,
                           "ascendant": c.ascendant, "midheaven": c.midheaven},
            from_date=date(2026, 9, 1), to_date=date(2026, 9, 30),
            today=TODAY, user_timezone="Europe/Moscow", tier=tier,
            week_offset=week_offset,
        )

    def test_week_days_still_cover_exactly_one_week(self):
        """Вкладка «Неделя» осталась недельной, а не стала окном ленты."""
        for offset in (0, 1, 2):
            days = self._planner(week_offset=offset)["week_days"]
            assert 2 <= len(days) <= 6, f"offset={offset}: {len(days)} проходов"

    def test_week_nav_is_intact(self):
        nav = self._planner(week_offset=1)["week_nav"]
        assert nav["week_offset"] == 1
        assert nav["total_weeks"] >= 4
        assert nav["week_start"] < nav["week_end"]

    def test_labels_keep_real_times(self):
        """Метки остались «дд.мм Дн ЧЧ:ММ» и без полуночной обрезки."""
        import re
        days = self._planner(week_offset=0)["week_days"]
        for d in days:
            assert re.fullmatch(r"\d{2}\.\d{2} \S{2} \d{2}:\d{2}", d["date"]), d["date"]
            assert re.fullmatch(r"\d{2}\.\d{2} \S{2} \d{2}:\d{2}", d["time"]), d["time"]

    def test_feed_and_planner_agree_to_the_minute(self):
        """Одно и то же время в ленте и в /planner/monthly — до минуты.

        ⚠️ Ради этого теста задание и ставилось. На приёмке 16.09.2026
        приложение показывало проход на +3 часа позже веба, и по двум экранам
        нельзя было сказать, который врёт. Истина установлена прямым расчётом
        мимо обоих (долгота Луны против куспидов, бисекция по swisseph):
        вход в 1 дом на этой карте — 12.09.2026 13:03 по Europe/Moscow, и
        именно это отдаёт движок домов.

        Расхождение было в ЛЕНТЕ и чинится флагом `local=True` у `add()`
        (feed/builder.py): движок домов отдаёт проходы Луны МЕСТНЫМ временем,
        а лента объявляла его UTC ещё раз. Тест сверяет два экрана между
        собой — то есть ловит возврат любого одностороннего сдвига.
        """
        from backend.transit.planner_engine import build_planner
        c = _chart()
        planner = build_planner(
            natal_profile={"planets": c.planets, "houses": c.houses,
                           "ascendant": c.ascendant, "midheaven": c.midheaven},
            from_date=date(2026, 9, 1), to_date=date(2026, 9, 30),
            today=date(2026, 9, 16), user_timezone="Europe/Moscow",
            tier="pro", week_offset=None, now=datetime(2026, 9, 16, 12, 0),
        )
        # «12.09 Сб 13:03» → ключ «12.09 13:03»
        def key_from_label(label: str) -> str:
            day, _weekday, clock = label.split()
            return f"{day} {clock}"

        web = {key_from_label(d["date"]) for d in planner["week_days"]}
        assert web, "неделя веб-планера пуста — сверять нечего"

        feed_cache.clear()
        feed = build_feed(chart=_chart(), from_date=date(2026, 9, 1), to_date=date(2026, 9, 30),
                          today=date(2026, 9, 16), tier="pro", now=datetime(2026, 9, 16, 12, 0))
        app = {f"{e['at'][8:10]}.{e['at'][5:7]} {e['at'][11:16]}"
               for e in feed["events"] if e["kind"] == "planner_moon_house"}

        common = web & app
        assert common, (
            "ни один проход не совпал по времени между лентой и планером. "
            f"планер: {sorted(web)} | лента: {sorted(app)}"
        )
        # Каждый проход НЕДЕЛИ планера обязан найтись в ленте тем же временем.
        assert web <= app, f"в ленте нет этих проходов планера: {sorted(web - app)}"

    def test_free_now_gets_the_current_week_open(self):
        """Правка сетки доехала и до веба: free видит текущую неделю.

        ⚠️ Это ИЗМЕНЕНИЕ выдачи `/planner/monthly`, единственное и намеренное
        (решение владельца 16.09.2026). Всё остальное в ответе прежнее —
        см. проверки выше.
        """
        days = self._planner(tier="free", week_offset=None)["week_days"]
        assert any(not d["locked"] for d in days), (
            "у free не открылось ни одного прохода текущей недели"
        )
        assert any(d["groups"] for d in days if not d["locked"])
