"""Тексты планера: словарь продукта (задание владельца 28.09.2026, раздел 4).

Сканирует ВСЕ строки methodology.json и заголовки планет ленты
(house_passages.PLANET_SUBTITLES):
* нет «ИИ»/«AI» (голос продукта), эзотерики («эзотерик», «чакр», «карм»,
  «магическ», «Вселенн»), «т.д» без пробела, «беременн»;
* нет обрыва заголовка: строка не кончается предлогом или «в темах» — так
  висели «…получения удовольствия через» и «…ремонта в темах».

Правки текстов — docs/planner_texts_review.md; свои тексты противоположных
домов Урана, Нептуна и Плутона — docs/planner_axis_texts.md.
"""
import json
import re
from pathlib import Path

import pytest

from backend.transit.house_passages import PLANET_SUBTITLES

SRC = Path(__file__).resolve().parents[1] / "transit" / "methodology.json"

# С 29.09.2026 (вычитка Луны по домам): «гуру», «места силы», «нумеролог» —
# эзотерика; «подруг» — угадывание пола; «он-лайн» — орфография.
# ⚠️ Эзотерика — по КОРНЮ «эзотери»: до 03.10.2026 здесь стояло «эзотерик», и
# «эзотерическую практику» (Скорпион в NEWMOON_SIGN_RITUAL) тест не видел —
# «эзотерич…» с «эзотерик» не совпадает.
FORBIDDEN = re.compile(
    r"\bИИ\b|\bAI\b|эзотери|чакр|карм|магическ|Вселенн|т\.д|беременн"
    r"|\bгуру\b|мест\w* силы|нумеролог|подруг|он-лайн",
    re.I,
)
# Предлоги, на которых строка обрываться не может, и «в темах».
DANGLING = re.compile(
    r"(?:\s(?:в|во|на|по|через|для|к|ко|с|со|о|об|от|из|у|за|при|про|без|до|над|под)|в темах)\s*$",
    re.I,
)


def _strings():
    def walk(x, path):
        if isinstance(x, dict):
            for k, v in x.items():
                yield from walk(v, f"{path}/{k}")
        elif isinstance(x, list):
            for i, v in enumerate(x):
                yield from walk(v, f"{path}/{i}")
        elif isinstance(x, str) and x:
            yield path, x
    yield from walk(json.loads(SRC.read_text(encoding="utf-8")), "")
    for k, v in PLANET_SUBTITLES.items():
        yield f"PLANET_SUBTITLES/{k}", v


STRINGS = list(_strings())


def test_scanner_sees_the_texts():
    assert len(STRINGS) > 800


@pytest.mark.parametrize("path,text", STRINGS, ids=[p for p, _ in STRINGS])
def test_no_forbidden_words(path, text):
    assert not FORBIDDEN.search(text), f"{path}: {text}"


@pytest.mark.parametrize("path,text", STRINGS, ids=[p for p, _ in STRINGS])
def test_no_dangling_heading(path, text):
    assert not DANGLING.search(text), f"{path}: {text}"


# После двоеточия в пунктах — строчная («Быт: покупка…», решение владельца
# 29.09.2026). Имена собственные — исключение: «Осторожно: Венера здесь…».
CAPITAL_AFTER_COLON = re.compile(r":\s+«?(?!Венер|Нептун|Меркури|Марс|Юпитер|Сатурн|Уран|Плутон|Солнц|Лун)[А-ЯЁ][а-яё]")
ITEMS = [(p, t) for p, t in STRINGS if "/items/" in p]


def test_lowercase_after_colon_in_items():
    bad = [f"{p}: {t}" for p, t in ITEMS if CAPITAL_AFTER_COLON.search(t)]
    assert len(ITEMS) > 400 and not bad, "\n".join(bad[:20])


def test_scanner_catches_known_breaks():
    assert DANGLING.search("Лучшее время для наполнения ресурсом, получения удовольствия через")
    assert DANGLING.search("…наведения порядка и ремонта в темах")
    assert FORBIDDEN.search("Используй ИИ для работы") and FORBIDDEN.search("родовой кармой")
    assert FORBIDDEN.search("Посещение мест силы") and FORBIDDEN.search("Встреча с подругами")
