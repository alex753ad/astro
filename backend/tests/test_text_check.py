"""Шаг 8: счётчики голоса продукта на текстах модели (interpretation/text_check.py)."""
from pathlib import Path

import pytest

from backend.interpretation import text_check
from backend.interpretation.text_check import check, report

BACKEND = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("text,kind", [
    ("Это подсказал ИИ.", "ai"),
    ("Модель AI считает так.", "ai"),
    ("Вам стоит отдохнуть.", "formal_you"),
    ("Ваша Луна сегодня спокойна.", "formal_you"),
    ("Проработай карму рода.", "esoteric"),
    ("Энергия Вселенной с тобой.", "esoteric"),
    ("Ритуал на новолуние.", "esoteric"),
    ("Ты уверена в себе.", "gendered"),
])
def test_catches(text, kind):
    assert kind in check(text), text


@pytest.mark.parametrize("text", [
    "Сегодня день для спокойных дел. Береги силы и выбери главное.",
    "Оптимистичный настрой поможет; магазин рядом.",  # «мисти», «маги» — не с начала слова
    "Вывод простой: выспись.",  # «вы» внутри слова
    "",
])
def test_clean(text):
    assert check(text) == {}


def test_report_counts_by_kind_and_contour(monkeypatch):
    seen = []
    monkeypatch.setattr("backend.forecast.stats.incr", lambda field, **kw: seen.append(field))
    n = report("Вам поможет ритуал, ты готова.", "chat")
    assert n == {"formal_you": 1, "esoteric": 1, "gendered": 1}
    # Прежний счётчик рода сохранён — его читает самопроверка.
    assert sorted(seen) == sorted(["gendered_you", "text:formal_you:chat",
                                   "text:esoteric:chat", "text:gendered:chat"])


def test_report_never_raises(monkeypatch):
    def boom(_text):
        raise RuntimeError("сбой")
    monkeypatch.setattr(text_check, "check", boom)
    assert report("любой текст", "chat") == {}


# Места, где модель пишет текст человеку. Новое место генерации — сюда и
# вызов report в нём; иначе счётчики шага 8 его не видят.
SITES = [
    "interpretation/router.py",       # разбор карты, PDF, сводка и PDF CRM, рассылка астролога
    "main.py",                        # разбор транзита
    "forecast/router.py",             # прогноз дня, лунации
    "interpretation/rag_router.py",   # чат
    "advanced_charts_router.py",      # соляр, синастрия, релокация
    "crm/router.py",                  # бриф к встрече
    "share_router.py",                # цитата «Поделиться»
]


@pytest.mark.parametrize("path", SITES)
def test_generation_sites_report(path):
    src = (BACKEND / path).read_text(encoding="utf-8")
    assert "text_check import report" in src, path
