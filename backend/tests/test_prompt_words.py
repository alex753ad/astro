"""Слова в подсказках промптов прогнозов (forecast_prompt.py) — тот же
сканер, что у текстов планера (test_planner_texts.FORBIDDEN), плюс мистика,
«целители», энергопрактики, рейки: эзотерика в голос продукта не входит
(решение владельца 29.09.2026)."""
import re

import pytest

import backend.transit.forecast_prompt as fp
from backend.tests.test_planner_texts import FORBIDDEN

EXTRA = re.compile(r"мисти|оккульт|целител|тонки\w* энерги|рейки|энергопрактик|энергетическ\w* практик", re.I)


def _strings():
    def walk(x, path):
        if isinstance(x, dict):
            for k, v in x.items():
                yield from walk(v, f"{path}/{k}")
        elif isinstance(x, (list, tuple)):
            for i, v in enumerate(x):
                yield from walk(v, f"{path}/{i}")
        elif isinstance(x, str):
            yield path, x
    for name in dir(fp):
        val = getattr(fp, name)
        if name.isupper() and isinstance(val, (dict, list, tuple)):
            yield from walk(val, name)


STRINGS = list(_strings())


def test_scanner_sees_the_hints():
    assert len(STRINGS) > 100


@pytest.mark.parametrize("path,text", STRINGS, ids=[p for p, _ in STRINGS])
def test_no_esoteric_words_in_prompt_hints(path, text):
    assert not FORBIDDEN.search(text) and not EXTRA.search(text), f"{path}: {text}"
