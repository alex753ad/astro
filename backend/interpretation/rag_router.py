"""RAG-чат по натальной карте — эндпоинт для Pro/Premium.

POST /api/v1/chart/{chart_id}/rag-chat
  body:  { "question": "...", "history": [{"role":"user","content":"..."}] }
  SSE stream: data: {"text": "..."} ... data: [DONE]

Требует тариф 'pro' или выше.
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
from backend.cache import budget_tracker
from backend.database import get_db, SessionLocal
from backend.limiter import limiter
from backend.models import NatalChart, User, AstreaMemory
from backend.interpretation.rag import retrieve, build_chart_summary, build_transits_block
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
OFF_TOPIC_REPLY = (
    "Это не моя тема — я говорю только про твою натальную карту и то, что "
    "в ней происходит. Спроси что-нибудь о карте, с радостью отвечу."
)

_TOPIC_CLASSIFIER_PROMPT = """Определи тему вопроса пользователя к астрологу. Ответь ровно одним словом: astrology или off_topic.

astrology — вопрос про натальную карту, транзиты, периоды; включая финансы, отношения, здоровье, карьеру ЧЕРЕЗ призму карты; включая вопросы о конкретных решениях (ипотека, операция, развод — это тоже astrology, там просто нужна оговорка про специалиста).
off_topic — курс валют, инфляция, ставка ЦБ, какие акции покупать, политика, новости, программирование и любые темы вне астрологии и вне карты человека.

Вопрос: {question}

Ответ одним словом:"""


async def _classify_topic(question: str) -> str:
    """'astrology' или 'off_topic'. При сбое классификации — fail open
    (astrology): сломанный классификатор не должен блокировать легитимный
    чат, у основной модели есть свои инструкции по границам как второй,
    более слабый слой (см. _system_prompt)."""
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
            raw = resp.json()["choices"][0]["message"]["content"].strip().lower()
            return "off_topic" if "off_topic" in raw else "astrology"
    except Exception as e:
        logger.warning("topic classification failed, defaulting to astrology: %s", e)
        return "astrology"


async def _off_topic_sse(user_id: str, chart_id: str, question: str, history: list[dict]):
    """Фиксированный, не сгенерированный моделью текст — ничего, что можно
    было бы уговорить переписать."""
    yield f"data: {json.dumps({'text': OFF_TOPIC_REPLY}, ensure_ascii=False)}\n\n"
    await _persist_turn(user_id, chart_id, question, OFF_TOPIC_REPLY, history)
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
    return f"""Тебя зовут Астрея. Ты — навигатор решений: помогаешь человеку понять его карту и выбрать, что делать и когда. Не предсказываешь судьбу.

Характер. Спокойная и собранная, говоришь ясно и по делу, без суеты и лишних восклицаний. Тепло проявляешь через пользу — не «всё будет хорошо», а «вот что сейчас сработает». Если тянут в гадание или мистику, мягко возвращаешь к тому, что видно в карте и что с этим делать.

Как пишешь. Просто и живо, как человек, а не как гороскоп. Без пафоса и общих фраз вроде «твой путь — раскрыть потенциал», без нанизанных красивых оборотов и обязательных троек. Конкретика вместо абстракций. Чередуй короткие и длинные фразы. Не выделяй жирным каждый термин.

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

## Границы: о чём Астрея говорит, а о чём нет

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



def _get_transits_block_cached(chart_id: str, chart_data: dict) -> str:
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
    block = build_transits_block(chart_data)

    now = datetime.now()
    midnight = datetime.combine(now.date() + timedelta(days=1), datetime.min.time())
    ttl = max(60, int((midnight - now).total_seconds()))
    chat_transits_cache.set(cache_key, block, ttl=ttl)
    return block


def _load_memory(db: Session, user_id: str) -> str:
    """Слой 2: читает сводку-память Астреи о пользователе (пустая строка, если нет)."""
    try:
        row = db.get(AstreaMemory, user_id)
        return row.summary if row and row.summary else ""
    except Exception as e:
        logger.warning("astrea memory load failed: %s", e)
        return ""


async def _update_memory(user_id: str, question: str, history: list[dict]) -> None:
    """Слой 2: сворачивает текущий диалог в память (фоново, после ответа).

    Один дешёвый вызов DeepSeek на реплику. Ошибки не критичны — память
    просто не обновится, чат от этого не страдает.
    """
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
                who = "Пользователь" if m.get("role") == "user" else "Астрея"
                lines.append(f"{who}: {content}")
            lines.append(f"Пользователь: {question}")
            dialog = "\n".join(lines)[:4000]

            fold_prompt = (
                "Ты ведёшь краткую память об одном человеке для ассистента Астреи.\n"
                f"Текущая сводка (может быть пустой):\n{current or '—'}\n\n"
                f"Новый диалог:\n{dialog}\n\n"
                "Обнови сводку: до 120 слов, от третьего лица, только устойчивые факты о "
                "человеке — его цели, решения, что он отметил сделанным, что советовала "
                "Астрея. Без приветствий и пояснений, верни только обновлённую сводку."
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
                new_summary = resp.json()["choices"][0]["message"]["content"].strip()

            if not new_summary:
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
    payload = {
        "model": settings.deepseek_model_flash,
        "messages": messages,
        "max_tokens": CHAT_MAX_TOKENS,
        "temperature": 0.7,
        "stream": True,
        "thinking": {"type": "disabled"},
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
                "text": "Не получилось сформировать ответ. Попробуйте ещё раз.",
            }
            yield f"data: {json.dumps(error_payload, ensure_ascii=False)}\n\n"
        else:
            await _persist_turn(user_id, chart_id, question, answer, history)
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
            "text": "Ответ не пришёл вовремя. Попробуйте ещё раз.",
        }
        yield f"data: {json.dumps(error_payload, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    except httpx.HTTPStatusError as e:
        logger.error("AI API error %s: %s", e.response.status_code, e.response.text[:200])
        fallback = "Извините, AI-сервис временно недоступен. Попробуйте через несколько минут."
        yield f"data: {json.dumps({'text': fallback}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"
    except Exception as e:
        logger.error("RAG stream error: user=%s chart=%s: %s", user_id, chart_id, e)
        error_payload = {
            "error": "stream_failed",
            "text": "Извините, что-то пошло не так. Попробуйте ещё раз.",
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
            detail="Дневной лимит AI-запросов исчерпан. Попробуйте завтра.",
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
    if topic == "off_topic":
        history = await _load_history(user.id, chart_id)
        return StreamingResponse(
            _off_topic_sse(user.id, chart_id, question, history),
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

    # Собираем system prompt (+ память Астреи о пользователе, слой 2,
    # + текущие транзиты, слой 3 — считаются раз в сутки на чарт, не на реплику)
    chart_summary = build_chart_summary(chart_data)
    memory_summary = _load_memory(db, user.id)
    transits_block = _get_transits_block_cached(chart_id, chart_data)
    system = _system_prompt(chart_summary, context_chunks, memory_summary, transits_block)

    # История берётся с сервера, а не из тела запроса: клиентская история
    # позволяла подделывать реплики ассистента и переопределять поведение модели.
    history = await _load_history(user.id, chart_id)
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
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
        background=BackgroundTask(_update_memory, user.id, question, history),
    )
