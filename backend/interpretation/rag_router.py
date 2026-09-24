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
from datetime import date

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.async_utils import iter_with_deadline
from backend.auth.dependencies import get_current_user, require_tier
from backend.auth.rate_limits import increment_monthly_usage, rag_chat_key
from backend.interpretation.router import track_engine_spend
from backend.cache import budget_tracker
from backend.database import get_db, SessionLocal
from backend.limiter import limiter
from backend.models import NatalChart, User, AstreaMemory
from backend.interpretation.rag import retrieve, build_chart_summary, build_transits_block
from backend.interpretation.address import ADDRESS_RULE
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
        "Про курсы, рынки и ставки не скажу — это не по карте, а гадать на "
        "деньгах я не берусь. Зато по твоей карте деньги видно хорошо: второй "
        "дом и его хозяин, Юпитер, транзиты по финансовым домам, ближайшие "
        "периоды возможностей и осторожности. С чего начнём?"
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

Ответь РОВНО ОДНИМ словом из списка: astrology, money, world, life.

astrology — всё, что можно разобрать по карте человека. Сюда входят:
- натальная карта, транзиты, периоды, планеты, дома, знаки, аспекты, узлы, ретроградность, стихии;
- финансы, отношения, семья, здоровье, работа, учёба, переезд — когда речь о жизни СОБЕСЕДНИКА;
- конкретные решения: ипотека, операция, развод, смена работы;
- ОДНО СЛОВО или короткая фраза без пояснения («дом», «деньги», «Сатурн», «отношения») — это просьба рассказать про эту тему по карте, а НЕ вопрос о внешнем мире.

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
    for label in OFF_TOPIC_REPLIES:
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
):
    """Фиксированный, не сгенерированный моделью текст — ничего, что можно
    было бы уговорить переписать.

    `topic` — метка от классификатора, ключ OFF_TOPIC_REPLIES. Неизвестная
    метка сюда не доходит (её `_classify_topic` уже свёл к astrology), но
    запасной текст всё равно есть: молчать в ответ на вопрос нельзя.
    """
    reply = OFF_TOPIC_REPLIES.get(topic, OFF_TOPIC_REPLY)
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
) -> str:
    kb_text = "\n".join(f"- {c}" for c in context_chunks) if context_chunks else "—"
    today = date.today().strftime("%d.%m.%Y")
    memory_block = ""
    if memory_summary:
        memory_block = (
            "\n## Что ты уже знаешь об этом человеке (из прошлых бесед):\n"
            f"{memory_summary}\n"
            "Опирайся на это, если уместно, но не пересказывай вслух без повода.\n"
        )
    return f"""Тебя зовут Аристея. Ты — навигатор решений: помогаешь человеку понять его карту и выбрать, что делать и когда. Не предсказываешь судьбу.

Характер. Спокойная и собранная, говоришь ясно и по делу, без суеты и лишних восклицаний. Тепло проявляешь через пользу — не «всё будет хорошо», а «вот что сейчас сработает». Если тянут в гадание или мистику, мягко возвращаешь к тому, что видно в карте и что с этим делать.

Как пишешь. Просто и живо, как человек, а не как гороскоп. Без пафоса и общих фраз вроде «твой путь — раскрыть потенциал», без нанизанных красивых оборотов и обязательных троек. Конкретика вместо абстракций. Чередуй короткие и длинные фразы. Не выделяй жирным каждый термин. {ADDRESS_RULE}

Сегодня {today}. Сроки и «окна» считай только от этой даты и вперёд, на прошедшие периоды не ссылайся.

{chart_summary}

{transits_block}
## Знания из базы под этот вопрос:
{kb_text}
{memory_block}
## Ты видишь и натальную карту, и текущие транзиты пользователя.
Отвечая на вопросы о настоящем моменте — опирайся на транзиты выше.
Отвечая на вопросы о характере и предрасположенностях — на натальную карту.
Не вычисляй астрономические данные сам, используй только переданные.
Если нужного транзита нет в списке выше — скажи, что сейчас его не видишь, не выдумывай.

## Границы:
1. Говори только по этой карте — конкретные планеты, знаки, дома. Никаких общих советов «для всех Тельцов».
2. Без страшилок и фатальных предсказаний. Напряжённое — зона работы, а не приговор.
3. Русский язык, 3–6 абзацев.

## Границы: о чём Аристея говорит, а о чём нет

Ты отвечаешь по натальной карте целиком — это твоя работа, не только часть тем.
Финансы, отношения, здоровье, карьера — всё разбираешь через дома, планеты,
аспекты и транзиты. Например, на вопрос «что моя карта говорит про деньги» —
разбираешь 2 дом, Юпитер, транзиты по финансовым домам, периоды возможностей.
Отказываться от таких вопросов нельзя.

Не твоя тема — внешний мир вне карты: курс валют, инфляция, ставка ЦБ, какие
акции покупать, политика, новости, программирование и любые темы вне
астрологии. Например, на «что будет с рублём в этом году» — вежливо откажись
и напомни, что говоришь только о карте этого человека, а не об экономике или
рынках.

Отдельно — вопросы о конкретном решении: «брать ли ипотеку», «делать ли
операцию», «разводиться ли». Здесь отказа нет. Отвечай астрологически: разбери
картину периода, покажи благоприятные и напряжённые аспекты, назови периоды
возможностей и осторожности. Заверши напоминанием, что это астрологическая
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



async def _get_transits_block_cached(chart_id: str, chart_data: dict) -> str:
    """Слой 3: транзиты на сегодня для этого чарта — раз в сутки, не на
    каждое сообщение чата (иначе каждая реплика пересчитывала бы эфемериды)."""
    from datetime import datetime, timedelta
    from backend.cache import chat_transits_cache

    today_str = date.today().isoformat()
    cache_key = f"chat_transits:{chart_id}:{today_str}"

    cached = chat_transits_cache.get(cache_key)
    if cached is not None:
        return cached

    from backend.interpretation.rag import build_transits_block
    # Swiss Ephemeris — синхронный, блокирует event loop (см. CLAUDE.md).
    # Кэш на сутки смягчает частоту, но первый вызов в дне всё равно бьёт
    # напрямую в event loop без этого.
    block = await asyncio.to_thread(build_transits_block, chart_data)

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


async def _sse_generator(
    messages: list[dict],
    tier: str,
    *,
    user_id: str = "",
    chart_id: str = "",
    question: str = "",
    history: list[dict] | None = None,
    turn: dict | None = None,
):
    """Стримит ответ от DeepSeek как SSE и дописывает диалог в серверную историю.

    20.08.2026: узел, где раньше терялся текст молча. finish_reason и факт
    reasoning_content логируются на пустом ответе — единственная зацепка,
    если thinking-флаг когда-нибудь перестанет действовать (смена модели,
    поведение провайдера) и это повторится.
    """
    collected: list[str] = []
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
                            collected.append(text)
                            yield f"data: {json.dumps({'text': text}, ensure_ascii=False)}\n\n"
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue

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
    user: User = Depends(require_tier("pro")),
    db: Session = Depends(get_db),
):
    """RAG-чат по натальной карте. Доступен для Pro и Premium.

    Лимит 20/час на аккаунт: эндпоинт вызывает LLM на каждую реплику и не
    списывался ни в UsageCounter, ни в дневной бюджет — один Pro-аккаунт мог
    выбрать весь дневной лимит расходов.
    """

    # Валидация
    question = body.question.strip()[:MAX_QUESTION_LEN]
    if not question:
        raise HTTPException(status_code=400, detail="Question is required")

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
        return StreamingResponse(
            _off_topic_sse(user.id, chart_id, question, history, topic),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    chart_data = {
        "planets":   chart.planets or [],
        "ascendant": chart.ascendant or {},
        "midheaven": chart.midheaven or {},
        "aspects":   chart.aspects or [],
        "houses":    chart.houses or [],
    }

    # RAG: получаем релевантные фрагменты
    context_chunks = retrieve(question, chart_data, top_k=6)

    # Собираем system prompt (+ память Аристеи о пользователе, слой 2,
    # + текущие транзиты, слой 3 — считаются раз в сутки на чарт, не на реплику)
    chart_summary = build_chart_summary(chart_data)
    memory_summary = _load_memory(db, user.id)
    transits_block = await _get_transits_block_cached(chart_id, chart_data)
    system = _system_prompt(chart_summary, context_chunks, memory_summary, transits_block)

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
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
        background=BackgroundTask(_update_memory, user.id, question, history, turn),
    )


@router.get("/api/v1/chart/{chart_id}/rag-chat/history")
async def rag_chat_history(
    chart_id: str,
    user: User = Depends(require_tier("pro")),
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
    карты нет вовсе). Тариф — тот же require_tier("pro").
    """
    chart = db.query(NatalChart).filter(
        NatalChart.id == chart_id,
        NatalChart.user_id == user.id,
    ).first()
    if not chart:
        raise HTTPException(status_code=404, detail="Chart not found")

    return {"messages": await _load_history(user.id, chart_id)}
