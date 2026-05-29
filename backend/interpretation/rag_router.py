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

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.auth.dependencies import get_current_user, require_tier
from backend.database import get_db
from backend.models import NatalChart, User
from backend.interpretation.rag import retrieve, build_chart_summary
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


def _system_prompt(chart_summary: str, context_chunks: list[str]) -> str:
    kb_text = "\n".join(f"- {c}" for c in context_chunks) if context_chunks else "—"
    return f"""Ты — опытный астролог-консультант. Отвечаешь на вопросы пользователя о его натальной карте.

{chart_summary}

## Релевантные знания из базы астрологии:
{kb_text}

## Правила:
1. Отвечай только по данным этой конкретной карты — не давай общих советов для всех Тельцов/Раков.
2. Ссылайся на конкретные планеты, знаки и дома из карты пользователя.
3. Тон: поддерживающий, не директивный. Без страшилок и фатальных предсказаний.
4. Если вопрос не связан с астрологией — мягко верни разговор к карте.
5. Отвечай на русском языке. Длина ответа: 3-6 абзацев.
"""


async def _stream_openai(messages: list[dict]) -> httpx.Response:
    payload = {
        "model": "gpt-4o",
        "messages": messages,
        "max_tokens": 800,
        "temperature": 0.7,
        "stream": True,
    }
    client = httpx.AsyncClient(timeout=60.0)
    resp = await client.send(
        client.build_request(
            "POST", _OPENAI_URL,
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        ),
        stream=True,
    )
    resp.raise_for_status()
    return resp, client


async def _stream_deepseek(messages: list[dict]) -> tuple:
    payload = {
        "model": "deepseek-chat",
        "messages": messages,
        "max_tokens": 800,
        "temperature": 0.7,
        "stream": True,
    }
    client = httpx.AsyncClient(timeout=60.0)
    resp = await client.send(
        client.build_request(
            "POST", _DEEPSEEK_URL,
            headers={
                "Authorization": f"Bearer {settings.deepseek_api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        ),
        stream=True,
    )
    resp.raise_for_status()
    return resp, client


async def _sse_generator(messages: list[dict], tier: str):
    """Стримит ответ от AI как SSE. GPT-4o для pro/premium, DeepSeek fallback."""
    use_gpt4o = tier in ("pro", "premium") and settings.openai_api_key

    try:
        if use_gpt4o:
            resp, client = await _stream_openai(messages)
        else:
            resp, client = await _stream_deepseek(messages)

        async with client:
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
        # fallback: простой текстовый ответ
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

    # Собираем system prompt
    chart_summary = build_chart_summary(chart_data)
    system = _system_prompt(chart_summary, context_chunks)

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
    )
