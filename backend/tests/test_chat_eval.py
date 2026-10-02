"""Проверки прогона вопросов к чату (scripts/chat_eval.py).

Прогон сравнивает «было | стало» по счётчикам нарушений. Если проверка
молча перестанет находить то, что должна, сравнение покажет «стало лучше»
на пустом месте — поэтому каждая проверка закреплена здесь и на находке, и
на чистом тексте.
"""
import importlib.util
from datetime import date
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "chat_eval", Path(__file__).resolve().parents[2] / "scripts" / "chat_eval.py")
ce = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ce)

_DAY = date(2026, 10, 2)
_SYSTEM = """Сегодня 02.10.2026.
  Солнце: Лев 9.8°, 3 дом
  Солнце квадрат Сатурн (орб 0.2034°)

Транзитная планета: Сатурн, 11°04' в знаке Овен, дом 11
Натальная планета: Луна, 11°04' в знаке Весы
Аспект: оппозиция, орб 0°00'
Точный аспект: 7 октября 2026
Период влияния: 11 сентября 2026 — 4 ноября 2026
"""


def test_clean_answer_has_no_violations():
    text = ("Сатурн в оппозиции к твоей Луне точнее всего 7 октября, держится до 4 ноября. "
            "Твоё Солнце в 3 доме, 9.8° Льва. Квадрат Солнца к Сатурну — про дисциплину.")
    c = ce.check(text, _SYSTEM, _DAY)
    assert not any(c[k] for k in ce.VIOLATIONS), c


def test_dates_outside_data():
    c = ce.check("Лучше всего с 12 по 15 ноября и 20.11.", _SYSTEM, _DAY)
    assert c["dates_not_in_data"] == ["12.11", "15.11", "20.11"]


def test_degree_is_not_a_date():
    assert ce.check("Солнце на 9.8° Льва.", _SYSTEM, _DAY)["dates_not_in_data"] == []


def test_aspect_outside_data():
    c = ce.check("Юпитер в трине к Венере открывает двери.", _SYSTEM, _DAY)
    assert c["aspects_not_in_data"]


def test_wrong_price_and_address():
    c = ce.check("Лира стоит 990 ₽. Вы можете отменить, ты уверен?", _SYSTEM, _DAY)
    assert c["wrong_prices"] == [990]
    assert c["formal_you"] == ["вы"]
    assert c["gendered"]


def test_date_windows_caught():
    """Окна, найденные владельцем в прогоне 02.10.2026, и их соседи."""
    text = ("Лучше во второй половине октября, ближе к концу месяца. "
            "Конец октября и ноябрь — спокойнее, первая половина недели — для разговоров.")
    found = [w.lower() for w in ce.check(text, _SYSTEM, _DAY)["date_windows"]]
    assert found == ["второй половине октября", "концу месяца", "конец октября", "первая половина недели"]


def test_date_windows_from_data_and_dated_are_clean():
    system = _SYSTEM + "Период: начало ноября.\n"
    text = "Это начало ноября. После 24 октября станет легче, до 21-го — терпение."
    assert ce.check(text, system, _DAY)["date_windows"] == []
