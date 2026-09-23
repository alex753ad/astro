"""Ручки прогнозов для приложения: на сегодня и на новолуние/полнолуние.

Контур 4 из CLAUDE.md («Прогнозы в приложении»). Отличия от прежних
/forecast/daily|weekly|monthly (удалены 23.09.2026) — и каждое намеренное:

* **Без квоты `transit_ai` и без гейта по тарифу.** Прогнозы для всех, включая
  free; списывай они `transit_ai`, free не получил бы ничего, а Вега сожгла
  бы свои 3 разбора в месяц за три дня — и витрина «разбор транзитов 3 в
  месяц» перестала бы быть правдой.
* **Запасной текст вместо 503.** Модель недоступна, бюджет исчерпан, ответ
  не прошёл проверку — человек всё равно получает прогноз (`fallback.py`).
* **Кэш — только ответ модели.** Запасной текст не кладётся: следующее
  открытие снова попробует модель.
* **Только владелец карты**: генерация стоит денег, анонимная карта по
  capability-токену сюда не пускается.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from backend.auth.dependencies import get_current_user
from backend.cache import budget_tracker, interpretation_cache
from backend.config import get_settings
from backend.database import get_db
from backend.forecast import facts as F
from backend.forecast.fallback import daily_fallback, lunation_fallback
from backend.forecast.prompts import (
    DAILY_PROMPT_VERSION, LUNATION_PROMPT_VERSION, build_daily_prompt, build_lunation_prompt,
    lunation_allowed, lunation_needs_warning,
)
from backend.forecast.validate import check_daily, check_lunation, parse_json_reply
from backend.limiter import limiter
from backend.models import User

logger = logging.getLogger("astro.forecast")
settings = get_settings()

router = APIRouter(prefix="/api/v1", tags=["forecast"])

DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"
# Ключ бюджета — тот же, по которому считается расход DeepSeek во всём
# проекте (track_engine_spend): общий суточный потолок один.
BUDGET_ENGINE = "deepseek"
MODEL_TIMEOUT_SEC = 60.0
ATTEMPTS = 2   # первый ответ + один повтор, потом запасной текст

TTL_TODAY = 2 * 86400
TTL_LUNATION = 45 * 86400


def _owned_chart(chart_id: str, user: User, db: Session):
    from backend.main import resolve_chart_access   # отложенно: main подключает этот роутер
    return resolve_chart_access(chart_id, user, None, db)


async def _ask_model(prompt: str, *, contour: str, json_mode: bool, max_tokens: int) -> str:
    """Один вызов DeepSeek Pro. Пустая строка — не удалось (причина в логе)."""
    if not settings.deepseek_api_key:
        return ""
    if not budget_tracker.is_within_budget(settings.ai_daily_budget_usd, BUDGET_ENGINE):
        logger.warning("%s: суточный бюджет исчерпан — запасной текст", contour)
        return ""
    body = {
        "model": settings.deepseek_model_pro,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.7,
        "stream": False,
        "thinking": {"type": "disabled"},
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    try:
        async with httpx.AsyncClient(timeout=MODEL_TIMEOUT_SEC) as client:
            resp = await client.post(
                DEEPSEEK_URL,
                headers={"Authorization": f"Bearer {settings.deepseek_api_key}"},
                json=body,
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.warning("%s: DeepSeek недоступен: %s", contour, e)
        return ""
    from backend.interpretation.router import track_engine_spend
    track_engine_spend(BUDGET_ENGINE, (data.get("usage") or {}).get("total_tokens") or 0, contour)
    try:
        return data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        return ""


# ── Сегодня ─────────────────────────────────────────────────

async def daily_forecast(chart, tz_name: str | None, today: date | None = None) -> dict:
    tz = F.resolve_tz(tz_name, chart.timezone)
    local_date = today or datetime.now(timezone.utc).astimezone(tz).date()
    key = f"forecast_today:v{DAILY_PROMPT_VERSION}:{chart.id}:{local_date.isoformat()}"
    cached = interpretation_cache.get(key)
    if cached is not None:
        return cached

    facts = await asyncio.to_thread(F.compute_day, chart, local_date, tz)
    prompt = build_daily_prompt(facts)
    paragraphs, source = None, "fallback"
    for attempt in range(ATTEMPTS):
        raw = await _ask_model(prompt, contour="forecast/today", json_mode=False, max_tokens=900)
        if not raw:
            break
        paras, problems = check_daily(raw)
        if not problems:
            paragraphs, source = paras, "model"
            break
        logger.warning("forecast/today: ответ отбракован (попытка %d): %s", attempt + 1, problems)
    if paragraphs is None:
        paragraphs = daily_fallback(facts)

    result = {
        "date": local_date.isoformat(),
        "paragraphs": paragraphs,
        "source": source,
        "trimmed": facts.trimmed,
    }
    if source == "model":
        interpretation_cache.set(key, result, ttl=TTL_TODAY)
    return result


@router.get("/chart/{chart_id}/forecast/today", summary="Прогноз на сегодня (приложение)")
@limiter.limit("20/minute")
async def get_forecast_today(
    request: Request,
    chart_id: str,
    tz: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    chart = _owned_chart(chart_id, user, db)
    return await daily_forecast(chart, tz)


# ── Новолуние / полнолуние ─────────────────────────────────

async def lunation_forecast(chart, phase: str, near: date, tz_name: str | None) -> dict:
    tz = F.resolve_tz(tz_name, chart.timezone)
    at_utc = await asyncio.to_thread(F.find_phase, phase, near)
    if at_utc is None:
        raise HTTPException(status_code=404, detail="Фаза рядом с этой датой не найдена.")
    # Ключ — по моменту фазы в UTC, а не по дате из запроса: запрос с соседней
    # даты попадает в тот же ключ. Пояс в ключе нужен: даты и время фазы в
    # тексте подписаны по местному времени читателя.
    key =f"forecast_lunation:v{LUNATION_PROMPT_VERSION}:{chart.id}:{phase}:{at_utc.strftime('%Y-%m-%dT%H:%M')}:{tz.key}"
    cached = interpretation_cache.get(key)
    if cached is not None:
        return cached

    facts = await asyncio.to_thread(F.compute_lunation, chart, phase, at_utc, tz)
    prompt = build_lunation_prompt(facts)
    dates, times = lunation_allowed(facts)
    need_warning = lunation_needs_warning(facts)
    block, source = None, "fallback"
    for attempt in range(ATTEMPTS):
        raw = await _ask_model(prompt, contour="forecast/lunation", json_mode=True, max_tokens=1500)
        if not raw:
            break
        parsed, problems = check_lunation(parse_json_reply(raw), dates, times, need_warning)
        if not problems:
            block, source = parsed, "model"
            break
        logger.warning("forecast/lunation: ответ отбракован (попытка %d): %s", attempt + 1, problems)
    if block is None:
        block = lunation_fallback(facts)

    result = {
        "phase": phase,
        "sign": facts.sign,
        "at": facts.at_local.isoformat(),
        **block,
        "source": source,
        "trimmed": facts.trimmed,
    }
    if source == "model":
        interpretation_cache.set(key, result, ttl=TTL_LUNATION)
    return result


@router.get("/chart/{chart_id}/forecast/lunation", summary="Прогноз на новолуние/полнолуние (приложение)")
@limiter.limit("20/minute")
async def get_forecast_lunation(
    request: Request,
    chart_id: str,
    phase: str,
    on_date: str = Query(..., alias="date"),
    tz: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """`date` — местная дата события из ленты (`moon_phase.at`), YYYY-MM-DD."""
    if phase not in ("new_moon", "full_moon"):
        raise HTTPException(status_code=422, detail="phase: new_moon или full_moon.")
    try:
        near = date.fromisoformat(on_date)
    except ValueError:
        raise HTTPException(status_code=422, detail="date: YYYY-MM-DD.")
    chart = _owned_chart(chart_id, user, db)
    return await lunation_forecast(chart, phase, near, tz)
