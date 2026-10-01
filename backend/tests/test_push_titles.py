"""Ни один заголовок пуша не начинается с ✦ (решение владельца 01.10.2026).

Приложение и веб: заголовки строит сервер (push/*.py — они же уходят в
локальные уведомления приложения через /push/upcoming), запасной заголовок
веба — в sw.js. Сканируем строковые литералы, а не вызовы: заголовок
собирается в десятке мест, и новый «✦ …» легко добавить мимо теста на
конкретный пуш.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCES = [*sorted((ROOT / "backend" / "push").glob("*.py")),
           ROOT / "backend" / "pdf_reports" / "build.py",
           ROOT / "frontend" / "public" / "sw.js"]


def test_no_push_title_starts_with_star():
    bad = [f"{p.relative_to(ROOT)}: {m.group(0)}"
           for p in SOURCES
           for m in re.finditer(r"""["']\s*✦[^"'\n]*""", p.read_text(encoding="utf-8"))]
    assert not bad, bad
