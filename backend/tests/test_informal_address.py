"""Продукт обращается к человеку на «ты» — решение владельца 24.09.2026.

Тест сканирует строки, которые может увидеть пользователь, и роняет прогон на
обращении на «вы»: местоимения («вы», «вас», «ваш»…), повелительное
наклонение («оформите», «попробуйте») и глаголы второго лица множественного
числа («можете», «станете»). Последние без местоимения не видны ни одному
грепу по «вы» — «важно не брать больше, чем можете осилить».

Что сканируется:
* Python (`backend/`, `bot/`) — только строковые литералы, включая части
  f-строк, через `ast`. Докстринги и комментарии не сканируются: это текст
  для разработчика, а не для человека.
* JSON (`backend/`) — все строковые значения.
* JS/JSX (`frontend/src`) — исходник без комментариев, то есть строки и
  JSX-текст. Тесты (`*.test.*`) не сканируются: они повторяют тексты кода, а
  где нарочно держат «вы» — это отрицательный пример.

Как выключить проверку для строки: маркер `вы-разрешено` в той же строке
исходника (в комментарии). Для файла целиком — `ALLOWED_FILES` с причиной.

⚠️ `PENDING` — временный список ещё не переведённых файлов, перевод идёт по
зонам (TASKS.md). Он только сокращается: файл, в котором нарушений больше
нет, обязан из него уйти — это проверяет отдельный тест, иначе список
превратился бы во второй, бессрочный белый.
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MARKER = "вы-разрешено"

_F = re.IGNORECASE | re.UNICODE
PRONOUN = re.compile(
    r"(?<![а-яё])(?:вы|вас|вам|вами|ваш|ваша|ваше|ваши|вашего|вашей|вашему|"
    r"вашим|вашими|ваших|вашу|вашем)(?![а-яё])", _F)
VERB_2PL = re.compile(r"(?<![а-яё])[а-яё]{2,}(?:айте|яйте|ейте|уйте|ойте|ьте|ите|ете|ёте)(?:сь)?(?![а-яё])", _F)
# Существительные на те же окончания (предложный падеж).
NOT_IMPERATIVE = {
    "сайте", "транзите", "лимите", "орбите", "визите", "защите", "кредите",
    "элите", "граните", "зените", "аппетите", "быте",
    "интернете", "кабинете", "ответе", "планете", "бюджете", "совете",
    "предмете", "секрете", "портрете", "пакете", "сюжете", "билете", "запрете",
    "комитете", "свете", "цвете", "ракете", "обете", "паритете", "приоритете",
    "авторитете", "факультете", "менталитете", "этикете", "буклете", "памфлете",
    "скелете", "силуэте", "куплете", "дуэте", "квартете", "омлете", "минарете",
}

# Файлы, где «вы» — намеренно. Причина обязательна.
ALLOWED_FILES = {
    # Юридические документы и текст согласия — не переводятся (решение
    # владельца 24.09.2026): формулировки согласованы как юридический текст.
    "frontend/src/pages/TermsPage.jsx": "оферта",
    "frontend/src/pages/PrivacyPage.jsx": "политика обработки данных",
    # Голос астролога, а не продукта: это видят КЛИЕНТЫ астролога (Орион),
    # и говорит с ними астролог, на «вы» (решение владельца 24.09.2026).
    "frontend/src/pages/PortalPage.jsx": "клиентский портал астролога",
    "frontend/src/pages/IntakePage.jsx": "анкета клиента астролога",
    "backend/crm/portal_router.py": "клиентский портал астролога",
    # Промпты об астрологе и его клиенте: модель пишет брифы астрологу о
    # третьем лице, обращения к человеку в них нет.
    "backend/crm/brief_prompt.py": "бриф астрологу о клиенте",
    "backend/crm/summary_prompt.py": "резюме астрологу о клиенте",
    # Карточка «Поделиться» пишется от первого лица, «вы» обращено к её
    # читателям (решение владельца 24.09.2026).
    "backend/share_router.py": "карточка от первого лица",
    # Проверка прогноза держит запрещённые формы как образец для отбраковки.
    "backend/forecast/validate.py": "список запрещённых форм",
}

# Временно: ещё не переведённые зоны. Только сокращается.
PENDING: set[str] = {
    "backend/auth/router.py",
    "backend/crm/dashboard_router.py",
    "backend/email_service.py",
    "backend/interpretation/template.py",
    "backend/lifecycle_emails.py",
    "backend/tasks.py",
    "backend/transit/methodology.json",
}


def _files():
    for base, pattern in (("backend", "**/*.py"), ("bot", "**/*.py"),
                          ("backend", "**/*.json"), ("frontend/src", "**/*.js"),
                          ("frontend/src", "**/*.jsx")):
        for p in (ROOT / base).glob(pattern):
            rel = p.relative_to(ROOT).as_posix()
            parts = set(p.parts)
            if parts & {"tests", "node_modules", "__pycache__", "alembic", "__preview__"}:
                continue
            if ".test." in p.name:
                continue
            yield rel, p


def _py_strings(src: str):
    tree = ast.parse(src)
    docstrings = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(body, list):
            for stmt in body:
                if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
                    docstrings.add(id(stmt.value))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
            # end_lineno, а не счёт переводов строк: у склеенных литералов
            # («...» "..." на соседних строках) переводов строк внутри нет,
            # а маркер может стоять на последней из них.
            yield node.lineno, node.end_lineno, node.value


def _json_strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            # `_readme` и подобные — записка для того, кто правит файл, а не
            # текст для человека.
            if k.startswith("_"):
                continue
            yield from _json_strings(k)
            yield from _json_strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _json_strings(v)


_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)
# `//` считается комментарием только в начале строки или после пробела —
# иначе резались бы адреса вида https://… внутри строк.
_LINE_COMMENT = re.compile(r"(?:^|(?<=\s))//.*$", re.M)


def _js_lines(src: str):
    # Блочные комментарии заменяются переводами строк, чтобы номера строк
    # остались верными.
    src = _BLOCK_COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"), src)
    src = _LINE_COMMENT.sub("", src)
    yield from enumerate(src.splitlines(), 1)


def _violations(text: str):
    out = [m.group(0) for m in PRONOUN.finditer(text)]
    out += [m.group(0) for m in VERB_2PL.finditer(text)
            if m.group(0).lower() not in NOT_IMPERATIVE]
    return out


def scan():
    """{файл: [(строка, слово, отрывок)]} — все нарушения вне белого списка."""
    result: dict[str, list] = {}
    for rel, p in _files():
        if rel in ALLOWED_FILES:
            continue
        src = p.read_text(encoding="utf-8-sig")
        lines = src.splitlines()
        found = []
        if p.suffix == ".py":
            for lineno, end, s in _py_strings(src):
                if any(MARKER in lines[i - 1] for i in range(lineno, min(end, len(lines)) + 1)):
                    continue
                for w in _violations(s):
                    found.append((lineno, w, s[:80]))
        elif p.suffix == ".json":
            for s in _json_strings(json.loads(src)):
                for w in _violations(s):
                    found.append((0, w, s[:80]))
        else:
            for lineno, line in _js_lines(src):
                if MARKER in lines[lineno - 1]:
                    continue
                for w in _violations(line):
                    found.append((lineno, w, line.strip()[:80]))
        if found:
            result[rel] = found
    return result


def test_no_formal_address():
    bad = {f: v for f, v in scan().items() if f not in PENDING}
    report = "\n".join(f"{f}:{ln}: «{w}» — {s}" for f, v in bad.items() for ln, w, s in v)
    assert not bad, "Обращение на «вы» в пользовательском тексте:\n" + report


def test_pending_is_not_stale():
    """Файл, в котором больше нет нарушений, обязан уйти из PENDING."""
    found = scan()
    stale = sorted(f for f in PENDING if f not in found)
    assert not stale, f"уже переведены, убрать из PENDING: {stale}"


def test_every_prompt_asks_for_ty():
    """Каждый промпт, текст которого читает человек, несёт ADDRESS_RULE.

    Сканер выше видит только литералы в коде, а текст модели — нет: без
    строки в промпте разбор заговорит на «вы», и ни один тест этого не
    заметит. Прогнозы (`forecast/prompts.py`) держат своё правило и свою
    проверку ответа (`forecast/validate.py`).
    """
    from backend.interpretation.address import ADDRESS_RULE
    from backend.interpretation import advanced_prompts as adv
    from backend.interpretation.base import InterpretationRequest
    from backend.interpretation.prompts import build_system_prompt
    from backend.interpretation.rag_router import _system_prompt
    from backend.transit import prompts as tp
    from backend.transit.forecast_prompt import build_general_calendar_prompt

    natal = build_system_prompt(InterpretationRequest(natal_profile={}, sections=["general"]))
    prompts = {
        "натальный разбор": natal,
        "соляр": adv.SOLAR_RETURN_PROMPT,
        "синастрия": adv.SYNASTRY_PROMPT,
        "релокация": adv.RELOCATION_PROMPT,
        "транзит": tp.TRANSIT_EVENT_PROMPT,
        "период транзитов": tp.TRANSIT_PERIOD_PROMPT,
        "чат": _system_prompt("карта", []),
        "календарь": build_general_calendar_prompt("Октябрь 2026", []),
    }
    missing = [name for name, text in prompts.items() if ADDRESS_RULE not in text]
    assert not missing, f"нет правила обращения на «ты»: {missing}"


def test_scanner_catches_known_forms():
    """Без этого тест выше был бы зелёным и на сломанном сканере."""
    assert _violations("Оформите Вегу, чтобы продолжить") == ["Оформите"]
    assert _violations("по вашей карте") == ["вашей"]
    assert _violations("о транзите на сайте") == []
    assert _violations("больше, чем можете осилить") == ["можете"]
    assert _violations("подпишитесь на канал") == ["подпишитесь"]
    assert list(_json_strings({"_readme": ["поправьте"], "a": "ваш"})) == ["a", "ваш"]
    assert list(_py_strings('"""док вы"""\nx = f"Ваш {y}"\n')) == [(2, 2, "Ваш ")]
    assert [l for _, l in _js_lines("a // Вы\n/* ваш */ b\n")] == ["a ", " b"]
    assert len(list(_files())) > 200
