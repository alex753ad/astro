"""Общие асинхронные помощники для потоковых ответов LLM: таймаут и
воспроизведение готового текста потоком.

20.08.2026: инцидент в чате Аристеи — httpx.AsyncClient(timeout=60.0) даёт
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
import re
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


# Размер порции и пауза подобраны в паре и не произвольны. Ими управляется не
# только внешний вид: фронт (`api/client.js`, flushBuffer) разбирает теги
# <section> в пределах ОДНОГО полученного события и делает это в два прохода —
# сперва все открывающие, затем все закрывающие. Поэтому единый большой чанк
# давал шесть section_start подряд до всякого текста: пустое оглавление, а
# весь разбор дописывался в последнюю секцию.
REPLAY_WORDS_PER_CHUNK = 8
REPLAY_CHUNK_DELAY = 0.02


async def replay_as_stream(
    text: str,
    step: int = REPLAY_WORDS_PER_CHUNK,
    delay: float = REPLAY_CHUNK_DELAY,
    keep_intact: "re.Pattern[str] | None" = None,
) -> AsyncIterator[str]:
    """Отдаёт готовый текст порциями, как если бы его писала модель.

    Нужен на попадании в кэш: там текст готов целиком, и без разбиения ушёл бы
    одним куском — приёмная сторона получила бы одно событие вместо сотни и
    повела себя иначе, чем при живой генерации.

    Отдаёт ТЕКСТ, а не готовые SSE-кадры: обрамление у вызывающих разное
    (interpretation/router.py отдаёт сырые чанки наверх, main.py заворачивает
    их в data:-кадры сам), общей является ровно нарезка.

    ⚠️ `keep_intact` — не украшение, без него фикс не работает. Совпадения
    этого шаблона отдаются ОТДЕЛЬНЫМИ порциями. Нужно там, где в тексте есть
    служебная разметка, порядок которой важен получателю: нарезка по словам
    склеивает `</section>` и следующий `<section name=...>` в одну порцию, а
    flushBuffer на фронте обрабатывает открывающие теги раньше закрывающих —
    и section_start следующей секции приходит ПЕРЕД section_end предыдущей.
    Текст между этими событиями тогда достаётся не той секции: замер на
    шести секциях по 25 слов дал 20 чужих слов из 150, по 2-6 в начале каждой
    секции. Симптом мягче исходного (оглавление не пустое), поэтому легко
    пропустить глазами. Изолированные теги порядок восстанавливают.

    Это лечение на стороне отдающего. Корень — в двухпроходном flushBuffer,
    который в принципе не сохраняет порядок; его переписывание — отдельная
    задача, см. CLAUDE.md.

    Пробел дописывается ко всем словесным порциям, кроме последней в своём
    сегменте, — иначе склейка на приёмной стороне потеряет разделители.

    Пауза линейна по объёму: 2500 слов -> ~310 порций -> ~6 с, 5000 слов ->
    ~12 с. Живая генерация того же объёма занимает кратно больше.
    """
    segments: list[tuple[str, bool]] = []
    if keep_intact is None:
        segments.append((text, False))
    else:
        pos = 0
        for m in keep_intact.finditer(text):
            if m.start() > pos:
                segments.append((text[pos:m.start()], False))
            segments.append((m.group(0), True))
            pos = m.end()
        if pos < len(text):
            segments.append((text[pos:], False))

    for segment, intact in segments:
        if not segment:
            continue
        if intact:
            yield segment
            await asyncio.sleep(delay)
            continue
        words = segment.split(" ")
        for i in range(0, len(words), step):
            piece = " ".join(words[i:i + step])
            if i + step < len(words):
                piece += " "
            if not piece:
                continue
            yield piece
            await asyncio.sleep(delay)
