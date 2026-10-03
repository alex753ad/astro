"""Прогон согласованности (scripts/consistency_eval.py): разбор блока чата и отчёт.

Разбор блока транзитов чата — единственное место прогона, которое читает
текст, а не данные. Перестанет находить даты — проверка c3 молча покажет
«0 из 0», то есть «расхождений нет» на пустом месте.
"""
import importlib.util
import json
from datetime import date
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "consistency_eval", Path(__file__).resolve().parents[2] / "scripts" / "consistency_eval.py")
ce = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ce)

_BLOCK = """## Текущие транзиты (на сегодня, посчитаны точно)

Транзитная планета: Сатурн, 11°04' в знаке Овен, дом 11, директный
Натальная планета: Луна, 11°04' в знаке Весы
Аспект: оппозиция, орб 0°00'
Точный аспект: 7 октября 2026
Период влияния: 11 сентября 2026 — 4 ноября 2026

Транзитная планета: Плутон, 2°10' в знаке Водолей, ретроградный
Натальная планета: Сев. узел, 2°00' в знаке Лев
Аспект: соединение, орб 0°10'
"""


def test_chat_block_parsed():
    assert ce.parse_chat_block(_BLOCK) == [
        {"transit": "Saturn", "natal": "Moon", "aspect": "opposition", "exact": date(2026, 10, 7)},
        {"transit": "Pluto", "natal": "North Node", "aspect": "conjunction", "exact": None},
    ]


def test_report_compares_runs(tmp_path):
    def run(bad):
        return {"meta": {"commit": "x", "date": "2026-10-03", "days": 7, "tzs": ["Europe/Moscow"], "tier": "premium"},
                "checks": {k: {"title": t, "compared": 2, "bad": bad if k == "c1" else [], "error": None}
                           for k, t in ce.CHECKS.items()}}
    cur, base = tmp_path / "cur.json", tmp_path / "base.json"
    cur.write_text(json.dumps(run(["новое"])), encoding="utf-8")
    base.write_text(json.dumps(run(["старое"])), encoding="utf-8")
    out = tmp_path / "r.md"
    ce.report(type("A", (), {"files": [str(cur), str(base)], "out": str(out)}))
    text = out.read_text(encoding="utf-8")
    assert "| c1 | Главное событие дня есть в ленте | 1 из 2 | 1 из 2 |" in text
    assert "* новое: новое" in text and "* ушло: старое" in text
