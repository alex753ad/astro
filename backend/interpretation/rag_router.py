"""RAG-чат по натальной карте — эндпоинты для Pro/Premium.

POST /api/v1/chart/{chart_id}/rag-chat
  body:  { "question": "...", "history": [{"role":"user","content":"..."}] }
  SSE stream: data: {"text": "..."} ... data: [DONE]

GET  /api/v1/chart/{chart_id}/rag-chat/history
  { "messages": [{"role":"user"|"assistant","content":"..."}] }

Оба требуют тариф 'pro' или выше.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from datetime import date

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.async_utils import iter_with_deadline
from backend.auth.dependencies import get_current_user
from backend.auth.rate_limits import increment_monthly_usage, rag_chat_key, tier_limiter
from backend.interpretation.router import track_engine_spend
from backend.cache import budget_tracker
from backend.database import get_db, SessionLocal
from backend.limiter import limiter
from backend.models import NatalChart, User, AstreaMemory
from backend.interpretation.rag import retrieve, build_chart_summary, build_transits_block, chat_chart_data
from backend.interpretation.address import ADDRESS_RULE
from backend.interpretation.chat_context import PRODUCT_TOPICS, WHERE_RULES, product_reply
from backend.flags import flag_on
from backend.redis_client import get_redis
from backend.config import get_settings

logger = logging.getLogger("astro.rag_router")
router = APIRouter(tags=["rag"])

settings = get_settings()

_OPENAI_URL = "https://api.openai.com/v1/chat/completions"
_DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"

MAX_HISTORY = 10   # максимум сообщений истории
MAX_QUESTION_LEN = 1000
HISTORY_TTL = 6 * 3600  # диалог живёт 6 часов бездействия

# 20.08.2026: инцидент — «прогноз на сегодня» вернул 200 и 14 байт (только
# data: [DONE]), ни одного символа текста. DeepSeek V4 по умолчанию reasoning
# (thinking.reasoning_effort="high") и тратит max_tokens на reasoning_content
# ДО финального ответа — то же самое, что уже было эмпирически найдено для
# интерпретаций (interpretation/deepseek.py) и вылечено там же полем
# "thinking": {"type": "disabled"}. В чат это поле не попало вообще ни в
# один из двух вызовов. Без reasoning-токенов на сам текст остаётся весь
# бюджет max_tokens — считаем как в interpretation/gpt4o.py:_calc_max_tokens
# (2.5 токена/слово), но с своей целью по длине.
# Чат: промпт просит 3–6 абзацев, берём верхнюю границу с запасом — 400 слов
# (не среднее, а худший случай, под который считается лимит) × 3 токена/слово
# (верхняя граница для русского, с учётом пунктуации/markdown) + 200 буфер.
CHAT_MAX_TOKENS = 1500
# Память: сводка до ~120 слов (см. промпт в _update_memory) × 3 + запас.
MEMORY_MAX_TOKENS = 400

# 20.08.2026: общий потолок на весь стрим чата (не per-chunk, см.
# backend/async_utils.py). Нет реальной телеметрии по скорости генерации
# DeepSeek Flash (боевого ключа нет в dev-окружении) — оценка сверху:
# типичный полный ответ на 3–6 абзацев (см. system prompt) заметно меньше
# потолка CHAT_MAX_TOKENS=1500 — ориентир ~1000–1200 токенов. При
# консервативной (нарочно заниженной, с запасом на сеть/провайдера) оценке
# скорости генерации ~35 ток/сек это ~30–35 сек — берём 45 сек, чтобы
# заведомо уложить нормальный ответ с запасом. Владелец наблюдала реальное
# ожидание ~65 сек до того, как решила, что чат завис (следующее сообщение
# «Ты тут?» в 08:20:57 против начала запроса в 08:19:52) — 45 сек заметно
# (на треть) ниже этого порога терпения, ошибка успевает показаться раньше,
# чем человек решит, что всё сломалось. Если реальные логи покажут другое
# распределение длительностей — пересмотреть на основе них, не оценки.
CHAT_STREAM_TIMEOUT = 45.0

# 20.08.2026: ограничение тем — отдельная проверка ДО основной модели, не
# только инструкция в system prompt. Промпт обходится уговорами внутри
# диалога, отдельный классификатор — нет: офф-топик вопрос никогда не
# доходит до модели с полным контекстом карты и базой знаний вообще.
# Ответы на чужую тему — по разновидности темы, а не один на все.
#
# ⚠️ Здесь до 09.09.2026 стоял ОДИН текст: «Это не моя тема — я говорю только
# про твою натальную карту… Спроси что-нибудь о карте». Он плох тем, что
# закрывает разговор, ничего не открывая: человек уже спросил, ему ответили
# «спроси другое», и что именно спрашивать — непонятно. На практике это
# особенно обидно ловилось на словах, у которых есть астрологическое значение
# (см. правку классификатора ниже).
#
# Теперь каждый ответ говорит ДВЕ вещи: чего Аристея не делает и что она по
# этому поводу может — с конкретными направлениями, из которых можно выбрать.
#
# ⚠️ Тексты по-прежнему ФИКСИРОВАННЫЕ, не сгенерированные моделью, и это
# главное свойство этого места: уговорить переписать нечего. Выбор идёт по
# закрытому набору меток, а не по тексту вопроса, — пользовательская строка в
# ответ не попадает ни при каком входе.
OFF_TOPIC_REPLIES = {
    "money": (
        # 02.10.2026, правка владельца: без «ближайших периодов возможностей»
        # — дат для этого у чата нет (правило «Даты» в промпте).
        "Про курсы, рынки и ставки не скажу — это не по карте. Зато по твоей "
        "карте деньги видно хорошо: второй и восьмой дома, их управители, "
        "транзиты по финансовым домам. С чего начнём?"
    ),
    "world": (
        "Новости и политику я не разбираю — там не моя работа. А вот твой "
        "собственный период посмотреть могу: что сейчас активно в карте, где "
        "напряжение, а где открытое окно, и на что это влияет в ближайшие "
        "месяцы. Посмотрим?"
    ),
    "life": (
        "Это уже не про карту, а туда я не лезу. Но если за вопросом стоит "
        "что-то твоё — работа, отношения, здоровье, крупное решение, — я "
        "разберу это по твоей карте: дома, планеты, транзиты и сроки. Про что "
        "рассказать?"
    ),
}

# Запасной текст: метка пришла незнакомая (модель ответила чем-то своим).
OFF_TOPIC_REPLY = OFF_TOPIC_REPLIES["life"]

_TOPIC_CLASSIFIER_PROMPT = """Ты определяешь, относится ли вопрос к работе астролога, который разбирает натальную карту собеседника.

Ответь РОВНО ОДНИМ словом из списка: astrology, money, world, life, tariffs, quota, cancel, navigation.

astrology — всё, что можно разобрать по карте человека. Сюда входят:
- натальная карта, транзиты, периоды, планеты, дома, знаки, аспекты, узлы, ретроградность, стихии;
- финансы, отношения, семья, здоровье, работа, учёба, переезд — когда речь о жизни СОБЕСЕДНИКА;
- конкретные решения: ипотека, операция, развод, смена работы;
- ОДНО СЛОВО или короткая фраза без пояснения («дом», «деньги», «Сатурн», «отношения») — это просьба рассказать про эту тему по карте, а НЕ вопрос о внешнем мире.

Вопросы о том, что Аристея помнит или знает о собеседнике, — тоже astrology.

tariffs — тарифы этого приложения (бесплатный, Вега, Лира, Орион), их цены и что в них входит. Вега, Лира и Орион — это тарифы, а не рынки.
quota — сколько сообщений или разборов осталось, какие лимиты.
cancel — отмена подписки, автопродление, возврат денег.
navigation — где в приложении или на сайте что найти, как открыть раздел.

money — только про рынки и экономику вообще, без связи с человеком: курс валют, инфляция, ставка ЦБ, какие акции или криптовалюту покупать.
world — политика, новости, войны, общественные события.
life — прочее, к карте отношения не имеющее: программирование, рецепты, погода, помощь с текстом, вопросы про саму нейросеть.

ГЛАВНОЕ ПРАВИЛО: если у слова или вопроса есть астрологическое прочтение — отвечай astrology. Сомневаешься — отвечай astrology.
Например: «дом» — это астрологический дом карты, а не недвижимость; «знак» — знак зодиака; «отношения» — синастрия и седьмой дом; «деньги» — второй дом. Все четыре примера это astrology.

Вопрос: {question}

Ответ одним словом:"""


def _label_from_reply(raw: str) -> str:
    """Ответ классификатора → метка темы.

    Вынесено отдельной функцией не ради красоты: это единственное МЕСТО, где
    решается «пропустить к модели или отбить», и проверять его через подделку
    HTTP-клиента значит проверять плумбинг, а не правило.

    ⚠️ Всё, что не опознано, — 'astrology'. Модель просит одно слово из
    закрытого набора, но ответить может чем угодно, и цена ошибки
    несимметрична: лишний вопрос к модели стоит копейки, отбитый настоящий
    вопрос про карту — ушедшего человека. Ровно это и происходило со словом
    «дом».
    """
    text = (raw or "").strip().lower()
    for label in (*PRODUCT_TOPICS, *OFF_TOPIC_REPLIES):
        if label in text:
            return label
    return "astrology"


async def _classify_topic(question: str) -> str:
    """Метка темы: 'astrology' (пропускаем к модели) либо ключ OFF_TOPIC_REPLIES.

    При сбое классификации — fail open (astrology): сломанный классификатор не
    должен блокировать легитимный чат, у основной модели есть свои инструкции
    по границам как второй, более слабый слой (см. _system_prompt).

    ⚠️ Незнакомая метка тоже трактуется как astrology, и это то же решение, а
    не отдельное: модель может ответить не тем словом, а цена ошибки
    несимметрична. Пропустить лишний вопрос к модели — потеря копеек; отбить
    настоящий вопрос про карту — человек уходит, решив, что чат не работает.
    Ровно это и происходило со словом «дом».
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                _DEEPSEEK_URL,
                headers={
                    "Authorization": f"Bearer {settings.deepseek_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.deepseek_model_flash,
                    "messages": [{"role": "user", "content": _TOPIC_CLASSIFIER_PROMPT.format(question=question)}],
                    "max_tokens": 5,
                    "temperature": 0.0,
                    "stream": False,
                    "thinking": {"type": "disabled"},
                },
            )
            resp.raise_for_status()
            raw = resp.json()["choices"][0]["message"]["content"]
            return _label_from_reply(raw)
    except Exception as e:
        logger.warning("topic classification failed, defaulting to astrology: %s", e)
        return "astrology"


async def _off_topic_sse(
    user_id: str, chart_id: str, question: str, history: list[dict], topic: str = "life",
    reply: str | None = None,
):
    """Фиксированный, не сгенерированный моделью текст — ничего, что можно
    было бы уговорить переписать.

    `topic` — метка от классификатора, ключ OFF_TOPIC_REPLIES. Неизвестная
    метка сюда не доходит (её `_classify_topic` уже свёл к astrology), но
    запасной текст всё равно есть: молчать в ответ на вопрос нельзя.
    """
    # `reply` — готовый ответ о продукте (chat_context.product_reply).
    reply = reply or OFF_TOPIC_REPLIES.get(topic, OFF_TOPIC_REPLY)
    yield f"data: {json.dumps({'text': reply}, ensure_ascii=False)}\n\n"
    await _persist_turn(user_id, chart_id, question, reply, history)
    yield "data: [DONE]\n\n"


class RagChatRequest(BaseModel):
    question: str
    # Поле оставлено ради совместимости со старым фронтом, но НЕ используется:
    # история берётся с сервера. Раньше клиент подавал сюда произвольные реплики
    # с role="assistant" и тем самым переписывал поведение модели — извлекал
    # системный промпт, содержимое базы знаний и авторские тексты Premium.
    history: list[dict] = []


def _history_key(user_id: str, chart_id: str) -> str:
    return f"rag:hist:{user_id}:{chart_id}"


async def _load_history(user_id: str, chart_id: str) -> list[dict]:
    """История диалога с сервера. При недоступном Redis — пустая (не ошибка)."""
    try:
        raw = await get_redis().get(_history_key(user_id, chart_id))
    except Exception as exc:  # noqa: BLE001
        logger.warning("rag history load failed: %s", exc)
        return []
    if not raw:
        return []
    try:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        items = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return []
    # Роли валидируем и на чтении: содержимое Redis может пережить смену формата.
    return [
        {"role": m["role"], "content": m["content"]}
        for m in items
        if isinstance(m, dict) and m.get("role") in ("user", "assistant") and m.get("content")
    ][-MAX_HISTORY:]


async def _save_history(user_id: str, chart_id: str, history: list[dict]) -> None:
    try:
        await get_redis().set(
            _history_key(user_id, chart_id),
            json.dumps(history[-MAX_HISTORY:], ensure_ascii=False),
            ex=HISTORY_TTL,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("rag history save failed: %s", exc)


def _system_prompt(
    chart_summary: str,
    context_chunks: list[str],
    memory_summary: str = "",
    transits_block: str = "",
    planner_block: str = "",
    today: date | None = None,
    p1_block: str = "",
) -> str:
    kb_text = "\n".join(f"- {c}" for c in context_chunks) if context_chunks else "—"
    # `today` — только для прогона вопросов (scripts/chat_eval.py), см. rag.py.
    today = (today or date.today()).strftime("%d.%m.%Y")
    memory_block = ""
    if memory_summary:
        memory_block = (
            "\n## Что ты уже знаешь об этом человеке (из прошлых бесед):\n"
            f"{memory_summary}\n"
            "Опирайся на это, если уместно, но не пересказывай вслух без повода.\n"
        )
    else:
        # Правило владельца 02.10.2026: вопрос о памяти идёт к модели (не в
        # отказ), а пустая память — честный ответ, а не выдуманные факты.
        memory_block = (
            "\nЕсли спрашивают, что ты помнишь, а сведений о прошлых разговорах нет — "
            "так и скажи: пока ничего не сохранила, а карту и текущие транзиты видишь.\n"
        )
    # Без планера (флаг выключен) промпт обязан совпадать с прежним до байта —
    # держит test_chat_planner_context.py.
    not_found = "нет в списке выше"
    planner_rules = ""
    if planner_block:
        not_found = "нет ни в транзитах, ни в планере"
        planner_rules = _PLANNER_RULES
    return f"""Тебя зовут Аристея. Ты — навигатор решений: помогаешь человеку понять его карту и выбрать, что делать и когда. Не предсказываешь судьбу.

Характер. Спокойная и собранная, говоришь ясно и по делу, без суеты и лишних восклицаний. Тепло проявляешь через пользу — не «всё будет хорошо», а «вот что сейчас сработает». Если тянут в гадание или мистику, мягко возвращаешь к тому, что видно в карте и что с этим делать.

Как пишешь. Просто и живо, как человек, а не как гороскоп. Без пафоса и общих фраз вроде «твой путь — раскрыть потенциал», без нанизанных красивых оборотов и обязательных троек. Конкретика вместо абстракций. Чередуй короткие и длинные фразы. Не выделяй жирным каждый термин. {ADDRESS_RULE}

Сегодня {today}. Сроки и «окна» считай только от этой даты и вперёд, на прошедшие периоды не ссылайся.

{chart_summary}

{transits_block}
{planner_block}{p1_block}## Знания из базы под этот вопрос:
{kb_text}
{memory_block}
## Ты видишь и натальную карту, и текущие транзиты пользователя.
Отвечая на вопросы о настоящем моменте — опирайся на транзиты выше.
Отвечая на вопросы о характере и предрасположенностях — на натальную карту.
Не вычисляй астрономические данные сам, используй только переданные.
Если нужного транзита {not_found} — скажи, что сейчас его не видишь, не выдумывай.
{_P0_RULES}{planner_rules}{WHERE_RULES if p1_block else ""}
## Границы:
1. Говори только по этой карте — конкретные планеты, знаки, дома. Никаких общих советов «для всех Тельцов».
2. Без страшилок и фатальных предсказаний. Напряжённое — зона работы, а не приговор.
3. Русский язык, 3–6 абзацев.

## Границы: о чём Аристея говорит, а о чём нет

Ты отвечаешь по натальной карте целиком — это твоя работа, не только часть тем.
Финансы, отношения, здоровье, карьера — всё разбираешь через дома, планеты,
аспекты и транзиты. Например, на вопрос «что моя карта говорит про деньги» —
разбираешь 2 дом, Юпитер и то, что из данных выше касается финансовых домов.
Отказываться от таких вопросов нельзя.

Не твоя тема — внешний мир вне карты: курс валют, инфляция, ставка ЦБ, какие
акции покупать, политика, новости, программирование и любые темы вне
астрологии. Например, на «что будет с рублём в этом году» — вежливо откажись
и напомни, что говоришь только о карте этого человека, а не об экономике или
рынках.

Отдельно — вопросы о конкретном решении: «брать ли ипотеку», «делать ли
операцию», «разводиться ли». Здесь отказа нет. Отвечай астрологически: разбери
картину периода по данным выше, покажи благоприятные и напряжённые аспекты из
них. Периоды возможностей и осторожности называй, только если их даты есть в
данных выше. Заверши напоминанием, что это астрологическая
картина, а само решение стоит принимать с профильным специалистом по теме
вопроса: про ипотеку и деньги — с финансовым консультантом, про операцию и
здоровье — с врачом, про развод и раздел имущества — с юристом. Не используй
одну и ту же фразу-заглушку для всех тем — специалист должен соответствовать
сути вопроса.

## Напоминание перед ответом
Ты говоришь только о натальной карте и транзитах этого человека — включая
финансы, отношения, здоровье, карьеру. Вопросы вне карты (курсы, экономика,
политика, новости, любые темы не про астрологию) — вежливый отказ с
напоминанием об этом. Вопросы о конкретных решениях — не отказ: разбери период
астрологически и заверши отсылкой к профильному специалисту по теме вопроса.
"""



# P0 по прогону вопросов 02.10.2026 (решение владельца), без флага.
# «Даты»: в прогоне A чат называл даты фаз, «лучших дней» и сроков, которых в
# данных нет (вопросы 6, 9, 10) — правило «не выдумывай» касалось только
# транзитов. «Это приложение»: чат называл наш пуш «сервисом, который
# показывает положение Луны», а прогноз дня — шаблоном по знаку Солнца
# (вопросы 2, 15): о том, что они из этого же приложения, модель не знала.
# Где посмотреть недостающее — P1 (названия разделов — таблицей владельцу).
_P0_RULES = """
## Даты
Любую дату, число или срок называй, только если он есть в данных выше. Сам дат не считай и не угадывай: ни фаз Луны, ни ретроградности, ни «удачных дней». Нужной даты в данных нет — так и скажи: точной даты сейчас не видишь.
Не составляй из дат свои окна и интервалы («с 4 ноября до начала декабря», «вторая половина месяца»), если такого отрезка нет в данных: называй даты и периоды ровно так, как они записаны выше.

## Это приложение
Человек пишет тебе из Aristea Timeline. Уведомления, прогноз дня, лента и планер — из этого же приложения и посчитаны по карте этого человека. Никогда не называй их чужим сервисом, общим гороскопом или шаблоном по знаку Солнца. Если человек спрашивает о них, а их текста у тебя нет, не пересказывай его наугад: скажи, что видишь его карту и текущие транзиты, и ответь по ним.
"""


# Правило согласовано владельцем 02.10.2026 (таблица до кода). Правило 7 —
# «Если это уже было в разговоре», а не «если уже говорила»: формулировка не
# должна подсказывать модели род — «ты» в продукте рода не угадывает
# (ADDRESS_RULE), правка владельца.
_PLANNER_RULES = """
## Сверяйся с планером
1. Человек видит этот планер в приложении. Твой ответ не должен ему противоречить.
2. О настоящем и ближайших неделях опирайся на планер и транзиты вместе: период планеты в доме — фон, транзитный аспект — его акцент.
3. Если аспекта к натальной планете нет, а в планере планета идёт по дому, говори о доме и сроках из планера, не отвечай «не вижу».
4. Если транзит добавляет напряжение к пункту планера, не отменяй пункт, а назови условие: что учесть и в какие дни.
5. Даты бери из планера как есть, не пересчитывай.
6. Пункты планера не перечисляй подряд. Выбери один-два под вопрос и объясни своими словами.
7. По периоду с пометкой «закрыт» назови только планету, дом и даты, советов для него не давай. Один раз за разговор, если в истории этого ещё не было, добавь коротко: «Подробнее этот период открыт на Веге» (или на Лире — как указано в строке). Если это уже было в разговоре, не повторяй.
"""


async def _get_p1_block(chart: NatalChart, user: User, zone: str | None, left, period, db) -> str:
    """Контекст P1 (флаг chat_planner_context): «День», «Ближайшее», тариф.

    Эфемеридные части — раз в сутки на карту, пояс и окно уведомлений (от
    окна зависит главное событие, как у пуша). Текст прогноза дня и остаток
    сообщений — на каждый вопрос: прогноз мог появиться в кэше днём, остаток
    меняется с каждым сообщением.
    """
    from backend.cache import chat_transits_cache, interpretation_cache
    from backend.forecast.facts import resolve_tz
    from backend.forecast.router import _daily_key
    from backend.interpretation import chat_context as cc
    from backend.push.cron import _daily_time_of, _quiet_from_of
    from backend.auth.rate_limits import usage_dates
    from backend.transit.planner_engine import now_local

    tzinfo = resolve_tz(zone, chart.timezone)
    today = now_local(tzinfo.key).date()
    daily, quiet = _daily_time_of(user), _quiet_from_of(user)

    forecast = interpretation_cache.get(_daily_key(chart.id, today, tzinfo.key))
    paragraphs = (forecast or {}).get("paragraphs") if isinstance(forecast, dict) else None

    key = f"chat_p1:{chart.id}:{tzinfo.key}:{daily}:{quiet}:{user.tier}:{today.isoformat()}"
    cached = chat_transits_cache.get(key)
    if cached is None:
        def build():
            return {
                "day": cc.day_block(chart, today, tzinfo.key, daily, quiet),
                "upcoming": cc.upcoming_block(chart, today, tzinfo.key, daily, quiet, user.tier),
            }
        try:
            cached = await asyncio.to_thread(build)
        except Exception as e:  # noqa: BLE001 — без P1 чат работает как раньше
            logger.warning("chat p1 context failed chart=%s: %s", chart.id, e)
            return ""
        chat_transits_cache.set(key, cached, ttl=6 * 3600)
    day = cached["day"]
    if paragraphs:
        day += "Текст прогноза дня, который человек видит:\n" + "\n".join(paragraphs) + "\n"
    dates = usage_dates(db, str(user.id)) if period == "month" else None
    return day + "\n" + cached["upcoming"] + "\n" + cc.tier_block(user.tier or "free", left, period, dates) + "\n"


def chat_timezone(tz: str | None, user, chart) -> str | None:
    """Пояс чата — как у ленты и планера (решение владельца 24.09.2026):
    `tz` запроса (приложение и веб шлют пояс устройства, `withTz`), иначе
    последний присланный пояс устройства (`users.device_timezone`, его же
    берут уведомления), иначе пояс карты. Мусор в `tz` — молча мимо."""
    from backend.time_utils import valid_timezone
    return (valid_timezone(tz) or valid_timezone(getattr(user, "device_timezone", None))
            or getattr(chart, "timezone", None))


async def _get_planner_block_cached(chart: NatalChart, tier: str, tz: str | None) -> str:
    """Планер для промпта (флаг chat_planner_context) — раз в сутки на карту,
    тариф и пояс: тариф в ключе, иначе после покупки чат до полуночи видел бы
    замки; пояс — иначе проходы Луны считались бы в поясе первого спросившего.

    Пояс — тот же, что у экрана планера (`chat_timezone`): телефон, иначе пояс
    карты. До 02.10.2026 здесь был только пояс карты.
    """
    from datetime import datetime, timedelta
    from backend.cache import chat_transits_cache
    from backend.interpretation.rag import build_planner_block
    from backend.transit.planner_engine import now_local

    if chart.time_unknown:
        return ""  # без времени рождения планера нет (/planner/monthly)
    now = now_local(tz)
    cache_key = f"chat_planner:{chart.id}:{tier}:{tz}:{now.date().isoformat()}"
    cached = chat_transits_cache.get(cache_key)
    if cached is not None:
        return cached

    natal_profile = {
        "planets":   chart.planets or [],
        "houses":    chart.houses or [],
        "ascendant": chart.ascendant or {},
        "midheaven": chart.midheaven or {},
    }
    # Swiss Ephemeris — синхронный, блокирует event loop (backend/CLAUDE.md).
    block = await asyncio.to_thread(build_planner_block, natal_profile, tier, tz, now.date())
    midnight = datetime.combine(now.date() + timedelta(days=1), datetime.min.time())
    chat_transits_cache.set(cache_key, block, ttl=max(60, int((midnight - now).total_seconds())))
    return block


async def _get_transits_block_cached(chart_id: str, chart_data: dict, tz: str | None = None) -> str:
    """Слой 3: транзиты на сегодня для этого чарта — раз в сутки, не на
    каждое сообщение чата (иначе каждая реплика пересчитывала бы эфемериды).

    «Сегодня» — местная дата человека (`chat_timezone`), а не сервера: контейнер
    живёт в UTC, и до 02.10.2026 с 00:00 до 03:00 МСК чат считал транзиты на
    вчера. Ключ — по местной дате: блок зависит только от даты."""
    from datetime import datetime, timedelta
    from backend.cache import chat_transits_cache
    from backend.transit.planner_engine import now_local

    local_today = now_local(tz).date()
    today_str = local_today.isoformat()
    # v2 (02.10.2026): даты пика — из чанков ленты. Без версии в ключе блоки
    # с прежними датами отдавались бы до полуночи после выката.
    cache_key = f"chat_transits:v2:{chart_id}:{today_str}"

    cached = chat_transits_cache.get(cache_key)
    if cached is not None:
        return cached

    from backend.interpretation.rag import build_transits_block
    # Swiss Ephemeris — синхронный, блокирует event loop (см. CLAUDE.md).
    # Кэш на сутки смягчает частоту, но первый вызов в дне всё равно бьёт
    # напрямую в event loop без этого.
    block = await asyncio.to_thread(build_transits_block, chart_data, 5, local_today, chart_id)

    now = datetime.now()
    midnight = datetime.combine(now.date() + timedelta(days=1), datetime.min.time())
    ttl = max(60, int((midnight - now).total_seconds()))
    chat_transits_cache.set(cache_key, block, ttl=ttl)
    return block


def _load_memory(db: Session, user_id: str) -> str:
    """Слой 2: читает сводку-память Аристеи о пользователе (пустая строка, если нет)."""
    try:
        row = db.get(AstreaMemory, user_id)
        return row.summary if row and row.summary else ""
    except Exception as e:
        logger.warning("astrea memory load failed: %s", e)
        return ""


async def _update_memory(
    user_id: str, question: str, history: list[dict], turn: dict | None = None,
) -> None:
    """Слой 2: сворачивает ЗАВЕРШЁННЫЙ ход диалога в память.

    Один дешёвый вызов DeepSeek на реплику. Ошибки не критичны — память
    просто не обновится, чат от этого не страдает.

    ⚠️ **`turn` — держатель, который заполняет `_sse_generator`, и он здесь
    нужен по существу, а не для удобства.** `BackgroundTask` связывает свои
    аргументы в момент СОЗДАНИЯ, то есть до того, как ответ модели существует.
    Пока сюда передавали только `question`, в свёртку уходил вопрос человека
    без ответа на него: ответ попадал в память лишь ходом позже, когда
    становился частью `history`, а последний ответ разговора — НИКОГДА.
    Замерено 09.09.2026: на первом ходу `history` пуста, и свёртка видела ровно
    одну строку — вопрос.

    Обиднее всего, что промпт свёртки прямо просит запомнить, «что советовала
    Аристея», — а именно свежего совета в данных и не было. Инструкция и данные
    расходились.

    Держатель решает это, не ломая жизненный цикл ответа: Starlette исчерпывает
    генератор и лишь ПОТОМ зовёт background (`stream_response` → `background()`
    в `starlette/responses.py`), то есть к этому моменту текст уже собран и
    записан в `turn`. Ждать свёртку внутри самого генератора было нельзя —
    это отложило бы `[DONE]` клиенту на всё время второго вызова модели.

    ⚠️ Нет ответа — не сворачиваем вовсе. Ход не состоялся: `_persist_turn` его
    тоже не записал, и памяти нечего запоминать, кроме вопроса в пустоту.
    """
    answer = (turn or {}).get("answer", "")
    if not answer:
        return
    try:
        db = SessionLocal()
        try:
            row = db.get(AstreaMemory, user_id)
            current = row.summary if row else ""

            lines: list[str] = []
            for m in history[-MAX_HISTORY:]:
                content = (m.get("content") or "").strip()
                if not content:
                    continue
                who = "Пользователь" if m.get("role") == "user" else "Аристея"
                lines.append(f"{who}: {content}")
            lines.append(f"Пользователь: {question}")
            lines.append(f"Аристея: {answer}")
            dialog = "\n".join(lines)[:4000]

            fold_prompt = (
                "Ты ведёшь краткую память об одном человеке для ассистента Аристеи.\n"
                f"Текущая сводка (может быть пустой):\n{current or '—'}\n\n"
                f"Новый диалог:\n{dialog}\n\n"
                "Обнови сводку: до 120 слов, от третьего лица, только устойчивые факты о "
                "человеке — его цели, решения, что он отметил сделанным, что советовала "
                "Аристея. Без приветствий и пояснений, верни только обновлённую сводку."
            )

            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(
                    _DEEPSEEK_URL,
                    headers={
                        "Authorization": f"Bearer {settings.deepseek_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": settings.deepseek_model_flash,
                        "messages": [{"role": "user", "content": fold_prompt}],
                        "max_tokens": MEMORY_MAX_TOKENS,
                        "temperature": 0.3,
                        "stream": False,
                        "thinking": {"type": "disabled"},
                    },
                )
                resp.raise_for_status()
                choice = resp.json()["choices"][0]
                finish_reason = choice.get("finish_reason")
                new_summary = choice["message"]["content"].strip()

            if not new_summary:
                return

            # ⚠️ Обрезанную сводку НЕ сохраняем, оставляем прежнюю. Тот же
            # приём, что в натальном разборе (`interpretation/router.py`: при
            # finish_reason != "stop" результат не кэшируется), и по той же
            # причине — незаконченный текст хуже отсутствующего.
            #
            # Здесь это особенно легко проглядеть: `MEMORY_MAX_TOKENS = 400` —
            # это примерно 130–160 русских слов, то есть чуть выше просимых в
            # промпте 120. Модель, перевыполнившая объём (а на коротких
            # заданиях она это делает устойчиво, см. CLAUDE.md «Объём разбора»),
            # упирается в потолок, ответ приходит с finish_reason="length" — и
            # до 09.09.2026 обрывок на полуслове ложился в БД молча и жил там,
            # подмешиваясь в КАЖДЫЙ следующий запрос чата.
            #
            # Прежняя сводка при этом не теряется: пропуск обновления оставляет
            # её как есть. Худшее последствие — память на один ход устарела.
            if finish_reason is not None and finish_reason != "stop":
                logger.warning(
                    "astrea memory fold ended with finish_reason=%s — сводка не сохранена "
                    "(user=%s, длина обрывка=%d)",
                    finish_reason, user_id, len(new_summary),
                )
                return

            new_summary = new_summary[:2000]

            if row:
                row.summary = new_summary
            else:
                db.add(AstreaMemory(user_id=user_id, summary=new_summary))
            db.commit()
        finally:
            db.close()
    except Exception as e:
        logger.warning("astrea memory update failed: %s", e)


async def _persist_turn(
    user_id: str,
    chart_id: str,
    question: str,
    answer: str,
    history: list[dict] | None,
) -> None:
    """Дописывает пару «вопрос-ответ» в серверную историю диалога."""
    if not (user_id and chart_id and question and answer):
        return
    updated = list(history or [])
    updated.append({"role": "user", "content": question})
    updated.append({"role": "assistant", "content": answer})
    await _save_history(user_id, chart_id, updated)


# ── Род в ответе чата (решение владельца 02.10.2026) ─────────────────────────
# Прогон вопросов нашёл «ты готова», «ты способен», «ты унаследовал», «быть
# жёсткой» при правиле ADDRESS_RULE в промпте: правило снижает частоту, но не
# гарантирует. Ответ идёт потоком, поэтому перегенерировать его ЦЕЛИКОМ нельзя
# — человек уже прочитал начало; держать весь ответ до конца — лишить чат
# потока (первые слова через 10–20 с вместо 1–2). Поэтому поток задержан на
# одну фразу: законченная фраза проверяется детектором прогнозов
# (gender_check.gendered_you) и при находке переписывается коротким вызовом.
# ⚠️ Прогон вопросов (scripts/chat_eval.py) идёт ЭТИМ ЖЕ генератором — иначе
# он мерил бы ответ, которого человек не видит.

_SENTENCE_END = re.compile(r"[.!?…]+[»\")\]]*\s+|\n+")

_GENDER_REWRITE_PROMPT = """Перепиши фрагмент ответа так, чтобы в нём не осталось слов, выдающих пол читателя. {address}

Найдено: {hits}.
Замени эти места оборотами без рода («у тебя хватит сил», «тебе подойдёт», «ты можешь», «себе», «держать твёрдость»), формы «готов(а)» тоже не годятся. Всё остальное — смысл, термины, даты, разметку и переносы строк — оставь как есть. Ответь только переписанным фрагментом.

Фрагмент:
{text}"""


def _split_ready(buf: str) -> tuple[str, str]:
    """(законченные фразы, хвост). Хвост ждёт следующих кусков потока."""
    last = None
    for last in _SENTENCE_END.finditer(buf):
        pass
    if last is None:
        return "", buf
    return buf[:last.end()], buf[last.end():]


async def _fix_gender(text: str, turn: dict | None) -> str:
    """Фраза без рода. Не вышло (сбой, пусто, снова род, длина уехала) —
    исходная фраза: незаконченный или искажённый ответ хуже оборота с родом,
    а остаток посчитает gender_report в _finish_turn."""
    from backend.interpretation.gender_check import gendered_you

    hits = gendered_you(text)
    if not hits:
        return text
    core = text.strip()
    lead, tail = text[:len(text) - len(text.lstrip())], text[len(text.rstrip()):]
    stats = turn if turn is not None else {}
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(
                _DEEPSEEK_URL,
                headers={"Authorization": f"Bearer {settings.deepseek_api_key}",
                         "Content-Type": "application/json"},
                json={
                    "model": settings.deepseek_model_flash,
                    "messages": [{"role": "user", "content": _GENDER_REWRITE_PROMPT.format(
                        address=ADDRESS_RULE, hits=", ".join(f"«{h}»" for h in hits), text=core)}],
                    "max_tokens": len(core) // 2 + 60,
                    "temperature": 0.2,
                    "stream": False,
                    "thinking": {"type": "disabled"},
                },
            )
            resp.raise_for_status()
            data = resp.json()
        fixed = (data["choices"][0]["message"]["content"] or "").strip()
        track_engine_spend("deepseek", (data.get("usage") or {}).get("total_tokens", 0), "rag_chat_gender")
    except Exception as e:  # noqa: BLE001 — переписывание не должно ронять ответ
        logger.warning("chat gender rewrite failed: %s", e)
        fixed = ""
    if fixed and not gendered_you(fixed) and 0.5 <= len(fixed) / max(len(core), 1) <= 2:
        stats["gender_rewrites"] = stats.get("gender_rewrites", 0) + 1
        return lead + fixed + tail
    stats["gender_unfixed"] = stats.get("gender_unfixed", 0) + 1
    logger.warning("chat gender rewrite rejected: hits=%s", hits[:3])
    return text


async def _sse_generator(
    messages: list[dict],
    tier: str,
    *,
    user_id: str = "",
    chart_id: str = "",
    question: str = "",
    history: list[dict] | None = None,
    turn: dict | None = None,
    quota_after: dict | None = None,
):
    """Стримит ответ от DeepSeek как SSE и дописывает диалог в серверную историю.

    `quota_after` — остаток сообщений ПОСЛЕ этого ответа ({left, period}): уходит
    кадром перед [DONE]. Само списание — фоном после потока (_finish_turn), и
    перезапрос остатка клиентом успевал раньше него — счётчик отставал на одно
    сообщение (приёмка 28.09.2026).

    20.08.2026: узел, где раньше терялся текст молча. finish_reason и факт
    reasoning_content логируются на пустом ответе — единственная зацепка,
    если thinking-флаг когда-нибудь перестанет действовать (смена модели,
    поведение провайдера) и это повторится.
    """
    collected: list[str] = []
    pending = ""
    finish_reason: str | None = None
    saw_reasoning = False
    stream_tokens = 0
    payload = {
        "model": settings.deepseek_model_flash,
        "messages": messages,
        "max_tokens": CHAT_MAX_TOKENS,
        "temperature": 0.7,
        "stream": True,
        "thinking": {"type": "disabled"},
        # Без include_usage DeepSeek не присылает счётчик токенов вовсе, и
        # расход чата было бы неоткуда взять, кроме как оценкой. Тот же
        # приём, что в interpretation/deepseek.py:89 — тот же провайдер.
        "stream_options": {"include_usage": True},
    }
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST", _DEEPSEEK_URL,
                headers={
                    "Authorization": f"Bearer {settings.deepseek_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            ) as resp:
                resp.raise_for_status()
                # httpx read-timeout сбрасывается на каждый чанк — не даёт
                # реального потолка на весь стрим (трикл-байты держат его
                # сколько угодно). iter_with_deadline — общий, не сбрасываемый
                # дедлайн на весь проход (backend/async_utils.py).
                async for line in iter_with_deadline(resp.aiter_lines(), CHAT_STREAM_TIMEOUT):
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                        if chunk.get("usage"):
                            stream_tokens = chunk["usage"].get("total_tokens", 0)
                        choice = chunk.get("choices", [{}])[0]
                        if choice.get("finish_reason"):
                            finish_reason = choice["finish_reason"]
                        delta = choice.get("delta", {})
                        if delta.get("reasoning_content"):
                            saw_reasoning = True
                        text = delta.get("content", "")
                        if text:
                            # Поток идёт с задержкой в одну фразу: законченная
                            # фраза проверяется на род и только потом уходит
                            # (см. _fix_gender).
                            pending += text
                            ready, pending = _split_ready(pending)
                            if ready:
                                ready = await _fix_gender(ready, turn)
                                collected.append(ready)
                                yield f"data: {json.dumps({'text': ready}, ensure_ascii=False)}\n\n"
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue

        if pending:
            pending = await _fix_gender(pending, turn)
            collected.append(pending)
            yield f"data: {json.dumps({'text': pending}, ensure_ascii=False)}\n\n"
        if turn is not None:
            # Для прогона вопросов (scripts/chat_eval.py): он идёт этим же
            # генератором и берёт отсюда расход и причину остановки.
            turn["tokens"] = stream_tokens
            turn["finish_reason"] = finish_reason

        # Единая точка выхода что для литерала [DONE] от DeepSeek, что для
        # обрыва потока без него — раньше второй случай не слал [DONE]
        # клиенту вообще, и это расходилось с обработкой на фронте.
        answer = "".join(collected)
        if not answer:
            # 200 без текста — то, что случилось 20.08.2026 (см. коммит).
            # Раньше здесь молча уходил [DONE] без единого байта текста —
            # с точки зрения фронта неотличимо от начавшегося и зависшего
            # ответа. Явная ошибка вместо тихого «успеха».
            logger.error(
                "RAG chat empty response: user=%s chart=%s finish_reason=%s "
                "saw_reasoning=%s question=%r",
                user_id, chart_id, finish_reason, saw_reasoning, question[:120],
            )
            error_payload = {
                "error": "empty_response",
                "text": "Не получилось сформировать ответ. Попробуй ещё раз.",
            }
            yield f"data: {json.dumps(error_payload, ensure_ascii=False)}\n\n"
        else:
            # Ключ расхода — deepseek, тот же, по которому выше спрашивали
            # is_within_budget. Токены из usage провайдера, не оценка;
            # при их отсутствии track_spend ничего не пишет.
            track_engine_spend("deepseek", stream_tokens, "rag_chat")
            await _persist_turn(user_id, chart_id, question, answer, history)
            # Держатель для фоновой свёртки памяти. Заполняется РЯДОМ с
            # _persist_turn и по той же причине: здесь текст впервые существует
            # целиком. Свёртку запускает background у ответа — она выполнится
            # после того, как генератор исчерпан, то есть уже увидит это
            # значение (см. докстринг _update_memory).
            if turn is not None:
                turn["answer"] = answer
            if quota_after is not None:
                yield f"data: {json.dumps({'quota': quota_after}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    except asyncio.TimeoutError:
        # Общий дедлайн (CHAT_STREAM_TIMEOUT) сработал — DeepSeek не уложился
        # в отведённое время. Не претендуем, что частичный текст — законченный
        # ответ: не пишем в историю, но то, что уже успело прийти, оставляем
        # видимым в пузырьке (см. RagChat.jsx) — только сообщаем об обрыве.
        logger.error(
            "RAG chat stream deadline exceeded (%.0fs): user=%s chart=%s "
            "collected_chars=%d finish_reason=%s question=%r",
            CHAT_STREAM_TIMEOUT, user_id, chart_id, len("".join(collected)),
            finish_reason, question[:120],
        )
        # Недописанная фраза из буфера (поток задержан на фразу, см.
        # _fix_gender) — отдаём как есть: до неё человек видел всё, что
        # успело прийти, и так должно остаться. Переписывать после дедлайна —
        # ещё до 8 с ожидания поверх уже истёкших.
        if pending:
            yield f"data: {json.dumps({'text': pending}, ensure_ascii=False)}\n\n"
        error_payload = {
            "error": "timeout",
            "text": "Ответ не пришёл вовремя. Попробуй ещё раз.",
        }
        yield f"data: {json.dumps(error_payload, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    except httpx.HTTPStatusError as e:
        logger.error("AI API error %s: %s", e.response.status_code, e.response.text[:200])
        fallback = "Извини, сервис временно недоступен. Попробуй через несколько минут."
        yield f"data: {json.dumps({'text': fallback}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"
    except Exception as e:
        logger.error("RAG stream error: user=%s chart=%s: %s", user_id, chart_id, e)
        error_payload = {
            "error": "stream_failed",
            "text": "Извини, что-то пошло не так. Попробуй ещё раз.",
        }
        yield f"data: {json.dumps(error_payload, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"


@router.post("/api/v1/chart/{chart_id}/rag-chat")
@limiter.limit("20/hour", key_func=rag_chat_key)
async def rag_chat(
    request: Request,
    chart_id: str,
    body: RagChatRequest,
    tz: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """RAG-чат по натальной карте. С 28.09.2026 — на всех тарифах: free —
    3 сообщения на пробу, Вега — 30 в месяц, Лира и Орион — без лимита
    (tier_limiter.check_chat_limit). Списание — после выданного ответа.

    Лимит 20/час на аккаунт: эндпоинт вызывает LLM на каждую реплику и не
    списывался ни в UsageCounter, ни в дневной бюджет — один Pro-аккаунт мог
    выбрать весь дневной лимит расходов.
    """

    # Валидация
    question = body.question.strip()[:MAX_QUESTION_LEN]
    if not question:
        raise HTTPException(status_code=400, detail="Question is required")

    # Лимит сообщений тарифа — до модели; списание фоном после ответа.
    tier_limiter.check_chat_limit(user, db)
    from backend.auth.rate_limits import chat_quota, usage_dates
    _left, _period = chat_quota(db, user)
    quota_after = {"left": _left - 1, "period": _period} if _left is not None else None
    if quota_after and _period == "month":
        quota_after.update(usage_dates(db, str(user.id)))
        # Число для «30 сообщений на этот срок закончились» — с сервера.
        from backend.auth.rate_limits import TIER_FLAGS
        quota_after["limit"] = TIER_FLAGS[user.tier]["chat_per_month"]

    # Дневной бюджет AI — общий с остальными интерпретациями.
    if not budget_tracker.is_within_budget(settings.ai_daily_budget_usd, "deepseek"):
        raise HTTPException(
            status_code=503,
            detail="Дневной лимит запросов исчерпан. Попробуй завтра.",
        )

    # Месячный счётчик. Отдельный kind: чат — не интерпретация карты, смешивать
    # их в одном счётчике значит либо съедать оплаченные интерпретации репликами
    # в чате, либо наоборот. Считаем ДО стрима: ответ уезжает потоком, и после
    # его начала записать расход уже некуда — соединение может оборваться, а
    # токены у провайдера всё равно потрачены.
    increment_monthly_usage(db, user.id, "rag_chat")

    # Загрузка карты — до классификации темы: даже офф-топик вопрос не
    # должен обходить проверку владения картой (иначе можно писать в историю
    # чата под произвольным чужим/несуществующим chart_id).
    chart = db.query(NatalChart).filter(
        NatalChart.id == chart_id,
        NatalChart.user_id == user.id,
    ).first()
    if not chart:
        raise HTTPException(status_code=404, detail="Chart not found")

    # Ограничение тем — отдельная проверка ДО основной модели: офф-топик
    # вопрос никогда не должен доходить до модели с полным контекстом карты
    # и базой знаний (см. _classify_topic).
    topic = await _classify_topic(question)
    if topic != "astrology":
        history = await _load_history(user.id, chart_id)
        # ⚠️ У этого ответа НЕТ `background=`, то есть память здесь намеренно не
        # обновляется — это решение, а не забытый провод. Разведка 09.09.2026
        # искала «где свёртка пропускается молча» и нашла эту ветку пятой, уже
        # не зная, задумано так или нет; комментарий закрывает вопрос.
        #
        # Причина: сворачивать нечего. В памяти лежат «устойчивые факты о
        # человеке — его цели, решения, что советовала Аристея» (см. промпт в
        # _update_memory), а здесь человек спросил про то, о чём Аристея не
        # говорит, и получил фиксированный текст, который она не сочиняла.
        # Свернуть это значило бы записать в долговременную память, что человек
        # интересовался курсом доллара, — и потом подмешивать этот факт в каждый
        # запрос про его карту.
        #
        # В историю диалога (Redis) отказ при этом ПИШЕТСЯ, и это не
        # противоречие: там нужен связный разговор, чтобы модель понимала «про
        # это я уже отвечала отказом» и не повторялась. Разные хранилища —
        # разные задачи.
        # Вопрос о продукте — фиксированный ответ кодом (chat_context): цену,
        # остаток и условия возврата модели не доверяем. Сообщение не
        # списывается — как и отказ по чужой теме (нет _finish_turn).
        reply = None
        if topic in PRODUCT_TOPICS:
            dates = usage_dates(db, str(user.id)) if _period == "month" else None
            reply = product_reply(topic, user.tier or "free", _left, _period, dates)
        return StreamingResponse(
            _off_topic_sse(user.id, chart_id, question, history, topic, reply),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    time_unknown = bool(chart.time_unknown)
    chart_data = chat_chart_data({
        "planets":   chart.planets,
        "ascendant": chart.ascendant,
        "midheaven": chart.midheaven,
        "aspects":   chart.aspects,
        "houses":    chart.houses,
    }, time_unknown)

    # RAG: получаем релевантные фрагменты
    context_chunks = retrieve(question, chart_data, top_k=6)

    # Память Аристеи — одна на аккаунт и написана о самом человеке. В чат по
    # чужой карте (подруги, ребёнка) она не подмешивается и из него не
    # сворачивается: иначе «что ты обо мне знаешь» в карте подруги отвечал бы
    # фактами владельца аккаунта, а разговор о подруге осел бы в его памяти.
    # «Своя» — та же карта, по которой строятся письма и планер
    # (get_primary_chart: закреплённая, иначе последняя сохранённая).
    from backend.chart_utils import get_primary_chart
    own = get_primary_chart(db, user)
    own_chart = own is not None and own.id == chart.id

    # Собираем system prompt (+ память Аристеи о пользователе, слой 2,
    # + текущие транзиты, слой 3 — считаются раз в сутки на чарт, не на реплику)
    chart_summary = build_chart_summary(chart_data, time_unknown)
    memory_summary = _load_memory(db, user.id) if own_chart else ""
    zone = chat_timezone(tz, user, chart)
    transits_block = await _get_transits_block_cached(chart_id, chart_data, zone)
    planner_block = p1_block = ""
    if flag_on(db, "chat_planner_context", user):
        planner_block = await _get_planner_block_cached(chart, user.tier, zone)
        p1_block = await _get_p1_block(chart, user, zone, _left, _period, db)
    from backend.transit.planner_engine import now_local
    system = _system_prompt(chart_summary, context_chunks, memory_summary, transits_block, planner_block,
                            today=now_local(zone).date(), p1_block=p1_block)

    # История берётся с сервера, а не из тела запроса: клиентская история
    # позволяла подделывать реплики ассистента и переопределять поведение модели.
    history = await _load_history(user.id, chart_id)

    # Держатель завершённого хода: генератор кладёт сюда полный текст ответа,
    # фоновая свёртка памяти читает. Пустой словарь, а не строка, потому что
    # BackgroundTask связывает аргументы в момент создания — то есть ДО того,
    # как ответ существует; передать можно только ссылку на общий объект.
    turn: dict = {}

    messages = (
        [{"role": "system", "content": system}]
        + history
        + [{"role": "user", "content": question}]
    )

    return StreamingResponse(
        _sse_generator(
            messages,
            user.tier,
            user_id=user.id,
            chart_id=chart_id,
            question=question,
            history=history,
            turn=turn,
            quota_after=quota_after,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
        background=BackgroundTask(_finish_turn, user.id, user.tier, question, history, turn, own_chart),
    )


async def _finish_turn(user_id: str, tier: str, question: str, history: list, turn: dict,
                       own_chart: bool = True) -> None:
    """После ответа: свёртка памяти и списание сообщения.

    ⚠️ Списываем только выданный ответ (`turn["answer"]` кладёт генератор
    рядом с _persist_turn): обрыв, пустой ответ и таймаут сообщение не
    съедают — так же, как разборы транзитов (commit_transit_ai).

    `own_chart=False` — разговор о чужой карте: память не сворачиваем (см.
    rag_chat).
    """
    if own_chart:
        await _update_memory(user_id, question, history, turn)
    if not turn.get("answer"):
        return
    from backend.interpretation.gender_check import report as gender_report
    gender_report(turn["answer"], "chat")
    db = SessionLocal()
    try:
        tier_limiter.commit_chat(user_id, tier, db)
    except Exception as e:  # noqa: BLE001 — расход не должен ронять фон
        logger.warning("chat usage not committed user=%s: %s", user_id, e)
    finally:
        db.close()


@router.get("/api/v1/chart/{chart_id}/rag-chat/history")
async def rag_chat_history(
    chart_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Диалог, который сервер помнит по этой карте. Только для чтения.

    Зачем нужен: история живёт на сервере (Redis, `rag:hist:{user}:{chart}`,
    MAX_HISTORY реплик, HISTORY_TTL бездействия) и подмешивается в промпт при
    каждом вопросе, а прочитать её клиенту было нечем — маршрут у чата был
    ровно один, POST. На вебе это почти не видно (состояние живёт в React,
    пока не перезагрузили страницу), а в приложении шторку чата закрывают и
    открывают постоянно: человек видел пустое окно у модели, которая
    продолжает помнить разговор. Снаружи это неотличимо от потери данных.

    ⚠️ **Наружу уходят только реплики человека и ответы модели.** Ни
    системного промпта, ни базы знаний, ни памяти Аристеи (`astrea_memory`)
    здесь нет и быть не должно: ровно это уже вытаскивали через поданную
    клиентом историю с role="assistant" (см. докстринг RagChatRequest —
    из-за того случая история и переехала на сервер). Гарантия структурная,
    а не по недосмотру: в Redis ложится только то, что кладёт туда
    `_persist_turn` — пара «вопрос человека / ответ модели», — а `_load_history`
    вдобавок отбрасывает всё, чья роль не user и не assistant. Собирать ответ
    из чего-то ещё здесь нечем.

    ⚠️ **Ничего не достраиваем.** Отдаём то, что реально лежит в Redis:
    истории нет, она истекла по TTL или Redis недоступен — пустой список и
    200, а не ошибка. Пустой чат — нормальное состояние (первый вопрос по
    карте), и показывать на нём отказ значило бы ломать штатный путь ради
    сбоя, от которого чат и так не зависит: `_load_history` при недоступном
    Redis точно так же отдаёт пустую историю и вопрос всё равно уходит модели.

    Проверка владения картой — та же, что в POST, и по той же причине: без
    неё ручка стала бы оракулом чужих chart_id (200 с пустым списком там, где
    карты нет вовсе). Тариф не проверяется: чат с 28.09.2026 на всех тарифах.
    """
    chart = db.query(NatalChart).filter(
        NatalChart.id == chart_id,
        NatalChart.user_id == user.id,
    ).first()
    if not chart:
        raise HTTPException(status_code=404, detail="Chart not found")

    return {"messages": await _load_history(user.id, chart_id)}
