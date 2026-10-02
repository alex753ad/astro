"""Род в ответе чата: фраза с родом переписывается до того, как уйдёт человеку.

Держит решение 02.10.2026: поток задержан на одну фразу, фраза проверяется
gender_check и при находке переписывается. Прогон вопросов
(scripts/chat_eval.py) идёт этим же генератором.
"""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from backend.interpretation import rag_router


def _client(deltas: list[str], rewrite: str | None):
    """Поток ответа — `deltas`; post (переписывание) — `rewrite` или сбой."""

    class _Stream:
        def raise_for_status(self):
            pass

        async def aiter_lines(self):
            for d in deltas:
                yield "data: " + json.dumps({"choices": [{"delta": {"content": d}}]}, ensure_ascii=False)
            yield "data: [DONE]"

    class _Ctx:
        async def __aenter__(self):
            return _Stream()

        async def __aexit__(self, *exc):
            return False

    class _Post:
        def raise_for_status(self):
            if rewrite is None:
                raise RuntimeError("provider down")

        def json(self):
            return {"choices": [{"message": {"content": rewrite}}], "usage": {"total_tokens": 10}}

    class _C:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        def stream(self, *a, **kw):
            return _Ctx()

        async def post(self, *a, **kw):
            return _Post()

    return _C


async def _run(deltas, rewrite):
    turn: dict = {}
    texts = []
    with patch.object(rag_router.httpx, "AsyncClient", _client(deltas, rewrite)):
        async for frame in rag_router._sse_generator([{"role": "user", "content": "q"}], "pro", turn=turn):
            body = frame[6:].strip()
            if body and body != "[DONE]":
                texts.append(json.loads(body).get("text", ""))
    return "".join(texts), turn


@pytest.mark.asyncio
async def test_gendered_sentence_is_rewritten_before_sending():
    text, turn = await _run(
        ["Сатурн рядом. Ты гот", "ова к переменам, и это ", "видно.\n\nДальше — спокойнее."],
        "У тебя есть силы для перемен, и это видно.",
    )
    assert "готова" not in text
    assert "У тебя есть силы для перемен, и это видно." in text
    assert text.startswith("Сатурн рядом. ") and text.endswith("Дальше — спокойнее.")
    assert turn["answer"] == text  # в историю уходит то же, что увидел человек
    assert turn["gender_rewrites"] == 1


@pytest.mark.asyncio
async def test_rewrite_failure_keeps_original_text():
    text, turn = await _run(["Ты готова к переменам. Дальше."], None)
    assert text == "Ты готова к переменам. Дальше."
    assert turn["gender_unfixed"] == 1


@pytest.mark.asyncio
async def test_clean_answer_untouched():
    text, turn = await _run(["Ты можешь начать. ", "Это твой период."], "НЕ ДОЛЖНО ПРИЙТИ")
    assert text == "Ты можешь начать. Это твой период."
    assert "gender_rewrites" not in turn


@pytest.mark.asyncio
async def test_rewrite_still_gendered_is_rejected():
    text, turn = await _run(["Ты готова к переменам."], "Ты уверена в переменах.")
    assert text == "Ты готова к переменам."
    assert turn["gender_unfixed"] == 1
