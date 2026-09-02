"""tests/test_replay_as_stream.py — нарезка готового текста при попадании в кэш.

02.09.2026. Кэш-хит интерпретации отдавал весь текст одним `yield`
(`interpretation/router.py`), и фронт получал одно SSE-событие вместо сотни.
`flushBuffer` (`frontend/src/api/client.js`) разбирает теги `<section>` в
пределах одного события и **в два прохода**: сперва все открывающие, затем все
закрывающие, и лишь потом отдаёт текст. Из-за этого:

1. один большой кусок → шесть `section_start` подряд до всякого текста:
   оглавление пустое, весь разбор дописан в последнюю секцию;
2. нарезка просто по словам → `</section>` и следующий `<section name=…>`
   попадают в одну порцию, `section_start` следующей секции приходит ПЕРЕД
   `section_end` предыдущей, и слова на стыке достаются не той секции.
   Замер до фикса: 20 чужих слов из 150, по 2-6 в начале каждой секции.

Второй симптом мягче первого и глазами не ловится — секции выглядят
заполненными. Поэтому тесты ниже проверяют не «текст порезан», а именно
**изолированность тегов**: без неё фикс выглядит рабочим, не будучи им.

Тесты защищают отдающую сторону. Сам `flushBuffer` двухпроходный и порядок не
сохраняет в принципе — его переписывание отдельная задача (CLAUDE.md, раздел
«Кэш-хит обязан отдаваться порциями»). Пока она не сделана, эти проверки —
единственное, что стоит между регрессом и продом.
"""

from __future__ import annotations

import pytest

from backend.async_utils import REPLAY_WORDS_PER_CHUNK, replay_as_stream
from backend.interpretation.router import _SECTION_TAG_RE

SECTION_NAMES = ["general", "career", "relationships", "health", "finance", "spirituality"]
WORDS_PER_SECTION = 25


def _make_text() -> str:
    """Текст той же формы, что приходит от модели: шесть секций в тегах.

    Слова помечены именем своей секции (`career0`, `career1`, …) — так тест
    отличает «текст попал не в ту секцию» от «текста нет вовсе».
    """
    parts = []
    for name in SECTION_NAMES:
        body = " ".join(f"{name}{i}" for i in range(WORDS_PER_SECTION))
        parts.append(f'<section name="{name}">\n{body}\n</section>')
    return "\n".join(parts)


async def _collect(text: str, **kwargs) -> list[str]:
    # delay=0: пауза нужна только живому клиенту, тесту она добавила бы секунды.
    return [piece async for piece in replay_as_stream(text, delay=0, **kwargs)]


class TestKeepIntact:
    """С keep_intact — режим интерпретации натальной карты."""

    async def test_join_equals_original(self):
        """Склейка порций посимвольно равна исходному тексту.

        Главная проверка: нарезка не имеет права ни потерять, ни добавить ни
        одного символа. Пробел дописывается ко всем порциям, кроме последней в
        сегменте, — ошибка на единицу здесь склеила бы слова или размножила
        пробелы, а на экране это выглядит как опечатка модели.
        """
        text = _make_text()
        pieces = await _collect(text, keep_intact=_SECTION_TAG_RE)
        assert "".join(pieces) == text

    async def test_tags_arrive_isolated(self):
        """Каждый тег — отдельная порция, без прилипшего текста.

        Ровно это и лечит дефект: пока `</section>` и следующий
        `<section name=…>` едут в одной порции, двухпроходный flushBuffer
        меняет их местами.
        """
        text = _make_text()
        pieces = await _collect(text, keep_intact=_SECTION_TAG_RE)

        tag_pieces = [p for p in pieces if "<section" in p or "</section" in p]
        assert len(tag_pieces) == len(SECTION_NAMES) * 2, (
            f"тегов-порций {len(tag_pieces)}, ожидалось {len(SECTION_NAMES) * 2}"
        )
        for piece in tag_pieces:
            assert _SECTION_TAG_RE.fullmatch(piece), (
                f"порция несёт тег вместе с чем-то ещё: {piece!r}"
            )

    async def test_no_piece_carries_two_tags(self):
        """Ни в одной порции не встречаются два тега разом.

        Отдельно от предыдущего теста: тот проверяет форму порций с тегами,
        этот — что склейки `</section><section …>` не осталось нигде, включая
        порции, которые могли бы пройти fullmatch по случайности.
        """
        pieces = await _collect(_make_text(), keep_intact=_SECTION_TAG_RE)
        for piece in pieces:
            assert piece.count("<section") + piece.count("</section") <= 1, (
                f"два тега в одной порции: {piece!r}"
            )

    async def test_text_between_tags_is_chunked(self):
        """Текст между тегами всё-таки режется, а не едет одним куском.

        Без этой проверки тест выше прошёл бы и на реализации, которая просто
        выделяет теги, а весь остальной текст отдаёт целиком, — то есть на
        исходном дефекте номер один.
        """
        pieces = await _collect(_make_text(), keep_intact=_SECTION_TAG_RE)
        body_pieces = [p for p in pieces if not _SECTION_TAG_RE.fullmatch(p)]
        assert len(body_pieces) > len(SECTION_NAMES)
        for piece in body_pieces:
            assert len(piece.split()) <= REPLAY_WORDS_PER_CHUNK


class TestWithoutKeepIntact:
    """Без keep_intact — режим разбора транзитного события (`main.py`).

    Там служебной разметки в тексте нет, и нарезка должна оставаться обычной,
    по словам: параметр не имеет права менять поведение старого вызывающего.
    """

    async def test_join_equals_original(self):
        text = " ".join(f"слово{i}" for i in range(100))
        pieces = await _collect(text)
        assert "".join(pieces) == text

    async def test_plain_word_chunks(self):
        text = " ".join(f"слово{i}" for i in range(100))
        pieces = await _collect(text)
        assert len(pieces) == 100 // REPLAY_WORDS_PER_CHUNK + (
            1 if 100 % REPLAY_WORDS_PER_CHUNK else 0
        )
        for piece in pieces:
            assert len(piece.split()) <= REPLAY_WORDS_PER_CHUNK

    async def test_tags_are_not_isolated_without_the_flag(self):
        """Без флага теги НЕ выделяются — граница проходит по словам.

        Фиксирует, что изоляция тегов включается именно параметром, а не
        происходит сама. Иначе следующая правка могла бы «на всякий случай»
        сделать её безусловной и незаметно изменить формат потока транзитов.
        """
        text = _make_text()
        pieces = await _collect(text)
        assert "".join(pieces) == text
        assert not all(
            _SECTION_TAG_RE.fullmatch(p)
            for p in pieces
            if "<section" in p or "</section" in p
        )


class TestEdgeCases:
    async def test_empty_text_yields_nothing(self):
        assert await _collect("", keep_intact=_SECTION_TAG_RE) == []

    async def test_text_shorter_than_one_chunk(self):
        text = "три слова всего"
        assert "".join(await _collect(text)) == text

    @pytest.mark.parametrize("text", ['<section name="general">\n', "</section>\n"])
    async def test_text_that_is_only_a_tag(self, text):
        pieces = await _collect(text, keep_intact=_SECTION_TAG_RE)
        assert pieces == [text]
