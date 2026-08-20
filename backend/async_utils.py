"""Общий асинхронный таймаут-хелпер для потоковых ответов LLM.

20.08.2026: инцидент в чате Астреи — httpx.AsyncClient(timeout=60.0) даёт
таймаут НА КАЖДОЕ отдельное чтение из сокета, а не на весь запрос. Пока
провайдер шлёт хоть что-то (включая пустые keep-alive строки) раз в 60 сек,
таймаут не сработает никогда — соединение может висеть сколько угодно.
Тот же изъян обнаружился и в потоковых интерпретациях (_try_stream в
interpretation/router.py) — общего таймаута на стрим там не было вообще,
только per-request таймаут httpx с той же проблемой.

iter_with_deadline оборачивает любой async-итератор ОБЩИМ, не сбрасывающимся
дедлайном: каждое чтение ждёт не фиксированное время, а remaining — то, что
осталось от исходного timeout. Использовано и в rag_router.py (чат), и в
interpretation/router.py (интерпретации) — один и тот же баг, один фикс.
"""
from __future__ import annotations

import asyncio
from typing import AsyncIterator, TypeVar

T = TypeVar("T")


async def iter_with_deadline(aiter, timeout: float) -> AsyncIterator[T]:
    """Итерирует async-итератор с общим дедлайном на весь проход.

    В отличие от httpx read-timeout (сбрасывается на каждый успешный чанк),
    здесь дедлайн фиксирован от первого вызова и не продлевается — сколько бы
    трикл-байтов провайдер ни прислал, после timeout секунд итерация
    завершается asyncio.TimeoutError.
    """
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    ait = aiter.__aiter__()
    while True:
        remaining = deadline - loop.time()
        if remaining <= 0:
            raise asyncio.TimeoutError(f"stream exceeded {timeout}s overall deadline")
        try:
            item = await asyncio.wait_for(ait.__anext__(), timeout=remaining)
        except StopAsyncIteration:
            return
        yield item
