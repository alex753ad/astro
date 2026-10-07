"""Эзотерика в голос продукта не входит (решения владельца 29.09 и 03.10.2026).

Две проверки:
* словари подсказок forecast_prompt.py — полным списком test_planner_texts
  (FORBIDDEN: эзотерика + голос продукта) и EXTRA;
* широкая (с 03.10.2026): все строки модулей промптов и готовых текстов —
  пушей, виджета, сторис, писем, — `knowledge_base.json` (чат) и
  `templates.json` (лента). Здесь только эзотерика (ESOTERIC + EXTRA): «AI» в
  логах и «т.д» в коде к голосу продукта отношения не имеют. Докстринги не
  сканируются — это записки для программиста.

До 03.10.2026 тест видел только словари: «Эзотерическая практика на
полнолуние» в самом тексте промпта календаря проходила мимо, а «эзотерик»
не совпадал с «эзотерическую».
"""
import ast
import json
import re
from pathlib import Path

import pytest

import backend.transit.forecast_prompt as fp
from backend.tests.test_planner_texts import ESOTERIC, FORBIDDEN

# «мисти» — в ESOTERIC, с начала слова: подстрокой оно ловило «оптимистичный».
EXTRA = re.compile(r"оккульт|целител|тонки\w* энерги|рейки|энергопрактик|энергетическ\w* практик", re.I)
WIDE = re.compile(ESOTERIC, re.I)

BACKEND = Path(__file__).resolve().parents[1]

# Промпты моделей и готовые тексты для человека.
MODULES = [
    # промпты
    "transit/forecast_prompt.py", "transit/prompts.py", "forecast/prompts.py",
    "forecast/meanings.py", "forecast/fallback.py", "interpretation/prompts.py",
    "interpretation/advanced_prompts.py", "interpretation/address.py",
    "interpretation/rag_router.py", "interpretation/chat_context.py",
    "interpretation/template.py", "pdf_reports/sections.py",
    "crm/summary_prompt.py", "crm/brief_prompt.py",
    # пуши, виджет, сторис, письма, планер, лента
    "day_event.py", "story_card.py", "widget.py", "week_ahead.py", "first_week.py",
    "push/cron.py", "email_service.py", "lifecycle_emails.py",
    "transit/engine.py", "transit/house_passages.py",
]
JSONS = ["interpretation/knowledge_base.json", "feed/templates.json"]

# эзотерика-разрешено: точные фразы, которые слово называют, чтобы его ЗАПРЕТИТЬ
# модели, — или мёртвый код. Маркер в исходнике здесь не годится: фразы лежат
# внутри многострочных промптов, где комментарий стал бы текстом промпта, а
# освобождать промпт целиком — значит не видеть новую эзотерику в нём.
ЭЗОТЕРИКА_РАЗРЕШЕНО = {
    "Если тянут в гадание или мистику":
        "запрет в промпте чата (rag_router._system_prompt)",
    "Без эзотерики: ни «работы с энергиями», ни «энергии Вселенной»":
        "запрет в промпте разбора карты (interpretation/prompts.py)",
    "без эзотерики, без мистических обещаний, без слов «энергия Вселенной», «карма», «чакры»":
        "запрет в промпте PDF (pdf_reports/sections._STYLE)",
}


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
    # HOUSE_SPHERE_MAP: 12 домов × name/emoji/hint. Словари месячного планера
    # удалены 07.10.2026 (шаг 7) — отсюда 36, а не прежние > 100.
    assert len(STRINGS) >= 36


@pytest.mark.parametrize("path,text", STRINGS, ids=[p for p, _ in STRINGS])
def test_no_esoteric_words_in_prompt_hints(path, text):
    assert not FORBIDDEN.search(text) and not EXTRA.search(text), f"{path}: {text}"


def _py_strings(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    docstrings = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(body, list) and body and isinstance(body[0], ast.Expr) \
                and isinstance(body[0].value, ast.Constant):
            docstrings.add(id(body[0].value))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
            yield f"{path.relative_to(BACKEND).as_posix()}:{node.lineno}", node.value


def _json_strings(path: Path):
    def walk(x, at):
        if isinstance(x, dict):
            for k, v in x.items():
                if not k.startswith("_"):  # `_readme` — записка для того, кто правит файл
                    yield from walk(v, f"{at}/{k}")
        elif isinstance(x, list):
            for i, v in enumerate(x):
                yield from walk(v, f"{at}/{i}")
        elif isinstance(x, str):
            yield at, x
    yield from walk(json.loads(path.read_text(encoding="utf-8-sig")), path.relative_to(BACKEND).as_posix())


def _wide():
    for m in MODULES:
        yield from _py_strings(BACKEND / m)
    for j in JSONS:
        yield from _json_strings(BACKEND / j)


def _hits(text: str) -> list[str]:
    for allowed in ЭЗОТЕРИКА_РАЗРЕШЕНО:
        text = text.replace(allowed, "")
    return [m.group(0) for rx in (WIDE, EXTRA) for m in rx.finditer(text)]


def test_no_esoteric_words_in_prompts_and_texts():
    bad = [f"{where}: {hits}" for where, text in _wide() if (hits := _hits(text))]
    assert not bad, "\n".join(bad)


def test_wide_scan_sees_its_sources():
    """Сканер не должен молча ослепнуть: строки есть в каждом источнике, а
    каждое исключение ещё встречается (иначе оно прячет уже чужой текст)."""
    texts = list(_wide())
    for src in MODULES + JSONS:
        assert any(w.startswith(src) for w, _ in texts), src
    joined = "\n".join(t for _, t in texts)
    for allowed in ЭЗОТЕРИКА_РАЗРЕШЕНО:
        assert allowed in joined, f"исключение больше не встречается: {allowed}"


def test_wide_scan_catches_known_forms():
    assert _hits("проведи любую эзотерическую практику") == ["эзотери"]
    assert _hits("Мистический опыт и ритуалы") == ["Мисти", "ритуал"]
    assert _hits("оптимистичный магазин, магистраль, угаданный") == []
    assert _hits("начни день с аффирмации, разложи таро") == ["аффирмац", "таро"]
