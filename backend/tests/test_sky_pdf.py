"""PDF «Главные транзиты» из ядра (задание 4.7, флаг sky_event). Карта
вымышленная, как в test_sky.py; у каждого теста свой id карты."""
import types
from datetime import date

from backend.day_event import points
from backend.pdf_reports import sections
from backend.tests.test_sky import CHART

TZ = "Europe/Moscow"


def _items(cid, today, months=12, n=20):
    chart = types.SimpleNamespace(**CHART, id=cid, time_unknown=False)
    return {(t["planet"], t["natal"], t["kind"]): t
            for t in sections.main_transits(points(chart), today, months, n, chart, TZ)}


def test_loop_one_line_with_gap_and_touches():
    """Юпитер оппозиция ASC: одна строка — срок всего события, перерыв и
    касания в окне; формулировки — общие с разбором и чатом."""
    t = _items("test-sky-pdf-loop", date(2026, 12, 15))[("Jupiter", "Ascendant", "opposition")]
    assert t["when"] == "до 18 июля 2027, с перерывом с 24 января по 26 июня"
    assert t["exact"] == "2 января и 7 июля 2027"


def test_future_loop_starts_and_all_touches():
    t = _items("test-sky-pdf-future", date(2026, 10, 1))[("Jupiter", "Ascendant", "opposition")]
    assert t["when"] == "с 1 ноября 2026 по 18 июля 2027, с перерывом с 24 января по 26 июня"
    assert t["exact"] == "22 ноября 2026, 2 января и 7 июля 2027"


def test_without_flag_unchanged():
    chart = types.SimpleNamespace(**CHART, id="test-sky-pdf-off", time_unknown=False)
    old = sections.main_transits(points(chart), date(2026, 12, 15), 12, 20)
    assert old and not any("перерыв" in t["when"] for t in old)
