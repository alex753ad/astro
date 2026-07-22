"""RAG-чат по натальной карте — эндпоинт для Pro/Premium.

POST /api/v1/chart/{chart_id}/rag-chat
  body:  { "question": "...", "history": [{"role":"user","content":"..."}] }
  SSE stream: data: {"text": "..."} ... data: [DONE]

Требует тариф 'pro' или выше.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.auth.dependencies import get_current_user, require_tier
from backend.database import get_db, SessionLocal
from backend.models import NatalChart, User, AstreaMemory
from backend.interpretation.rag import retrieve, build_chart_summary, build_transits_block
from backend.config import get_settings

logger = logging.getLogger("astro.rag_router")
router = APIRouter(tags=["rag"])

settings = get_settings()

_OPENAI_URL = "https://api.openai.com/v1/chat/completions"
_DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"

MAX_HISTORY = 10   # максимум сообщений истории
MAX_QUESTION_LEN = 1000


class RagChatRequest(BaseModel):
    question: str
    history: list[dict] = []  # [{role: "user"|"assistant", content: "..."}]


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
3. Вопрос не про карту — коротко ответь и верни разговор к карте.
4. Русский язык, 3–6 абзацев.
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
                        "model": "deepseek-chat",
                        "messages": [{"role": "user", "content": fold_prompt}],
                        "max_tokens": 220,
                        "temperature": 0.3,
                        "stream": False,
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


async def _sse_generator(messages: list[dict], tier: str):
    """Стримит ответ от DeepSeek как SSE."""
    payload = {
        "model": "deepseek-chat",
        "messages": messages,
        "max_tokens": 800,
        "temperature": 0.7,
        "stream": True,
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
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str.strip() == "[DONE]":
                        yield "data: [DONE]\n\n"
                        return
                    try:
                        chunk = json.loads(data_str)
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        text = delta.get("content", "")
                        if text:
                            yield f"data: {json.dumps({'text': text}, ensure_ascii=False)}\n\n"
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue

    except httpx.HTTPStatusError as e:
        logger.error("AI API error %s: %s", e.response.status_code, e.response.text[:200])
        fallback = "Извините, AI-сервис временно недоступен. Попробуйте через несколько минут."
        yield f"data: {json.dumps({'text': fallback}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"
    except Exception as e:
        logger.error("RAG stream error: %s", e)
        yield "data: [DONE]\n\n"


@router.post("/api/v1/chart/{chart_id}/rag-chat")
async def rag_chat(
    chart_id: str,
    body: RagChatRequest,
    user: User = Depends(require_tier("pro")),
    db: Session = Depends(get_db),
):
    """RAG-чат по натальной карте. Доступен для Pro и Premium."""

    # Валидация
    question = body.question.strip()[:MAX_QUESTION_LEN]
    if not question:
        raise HTTPException(status_code=400, detail="Question is required")

    # Загрузка карты
    chart = db.query(NatalChart).filter(
        NatalChart.id == chart_id,
        NatalChart.user_id == user.id,
    ).first()
    if not chart:
        raise HTTPException(status_code=404, detail="Chart not found")

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

    # История + новый вопрос
    history = body.history[-MAX_HISTORY:]
    messages = (
        [{"role": "system", "content": system}]
        + [{"role": m["role"], "content": m["content"]} for m in history
           if m.get("role") in ("user", "assistant") and m.get("content")]
        + [{"role": "user", "content": question}]
    )

    return StreamingResponse(
        _sse_generator(messages, user.tier),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
        background=BackgroundTask(_update_memory, user.id, question, history),
    )
