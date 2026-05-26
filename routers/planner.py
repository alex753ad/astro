"""Planner router — Planner Engine endpoints."""

from __future__ import annotations

import logging
import os
import calendar as cal_mod
from datetime import date as date_type, timedelta

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.database import get_db
from backend.models import NatalChart
from backend.limiter import limiter

logger = logging.getLogger("astro")
settings = get_settings()

router = APIRouter(prefix="/api/v1/chart", tags=["planner"])


@router.get("/{chart_id}/planner/monthly", summary="Monthly planner — pure Python interpretation")
@limiter.limit(settings.rate_limit_anon)
async def get_monthly_planner(
    request: Request,
    chart_id: str,
    db: Session = Depends(get_db),
):
    from backend.transit.planner_engine import build_planner

    chart = db.query(NatalChart).filter(NatalChart.id == chart_id).first()
    if not chart:
        raise HTTPException(status_code=404, detail="Chart not found")

    if chart.time_unknown:
        return {"planner": {"error": "Время рождения неизвестно — планер недоступен."}}

    _tz = getattr(chart, "timezone", None)
    if _tz:
        try:
            import pytz
            from datetime import datetime as _dt
            today = _dt.now(pytz.timezone(_tz)).date()
        except Exception:
            today = date_type.today()
    else:
        today = date_type.today()

    month_start = today.replace(day=1)
    last_day    = cal_mod.monthrange(today.year, today.month)[1]
    month_end   = today.replace(day=last_day)

    natal_profile = {
        "planets":   chart.planets,
        "houses":    chart.houses,
        "ascendant": chart.ascendant,
        "midheaven": chart.midheaven,
    }

    planner = build_planner(
        natal_profile=natal_profile,
        from_date=month_start,
        to_date=month_end,
        today=today,
        user_timezone=_tz,
    )
    return {"planner": planner}


@router.get("/{chart_id}/forecast/daily", summary="Daily personal forecast (JSON via AI)")
@limiter.limit(settings.rate_limit_anon)
async def get_daily_forecast(
    request: Request,
    chart_id: str,
    on_date: str,
    db: Session = Depends(get_db),
):
    from backend.transit.engine import calculate_transits, get_active_transits
    from backend.transit.forecast_prompt import build_daily_forecast_prompt, parse_forecast_response

    chart = db.query(NatalChart).filter(NatalChart.id == chart_id).first()
    if not chart:
        raise HTTPException(status_code=404, detail="Chart not found")

    try:
        query_date = date_type.fromisoformat(on_date)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid date format. Use YYYY-MM-DD.")

    events = calculate_transits(
        natal_planets=chart.planets,
        from_date=query_date - timedelta(days=1),
        to_date=query_date + timedelta(days=1),
    )
    active = get_active_transits(events, query_date)
    events_dicts = [
        {
            "transit_planet": e.transit_planet,
            "natal_planet":   e.natal_planet,
            "aspect_type":    e.aspect_type,
            "peak_orb":       getattr(e, "peak_orb", getattr(e, "orb", 0)),
            "transit_sign":   getattr(e, "transit_sign", ""),
            "natal_sign":     getattr(e, "natal_sign", ""),
            "exact_date":     getattr(e, "exact_date", None),
            "applying":       getattr(e, "applying", True),
            "date":           getattr(e, "peak_date", getattr(e, "date", on_date)),
        }
        for e in active
    ]
    natal_profile = {
        "planets":      chart.planets,
        "houses":       chart.houses,
        "ascendant":    chart.ascendant,
        "midheaven":    chart.midheaven,
        "time_unknown": chart.time_unknown,
    }
    prompt = build_daily_forecast_prompt(date=on_date, transit_events=events_dicts, natal_profile=natal_profile)
    raw = await _call_ai(prompt, max_tokens=2000)
    if not raw:
        raise HTTPException(status_code=503, detail="AI forecast unavailable.")
    try:
        forecast = parse_forecast_response(raw)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse forecast: {e}")
    return {"date": on_date, "forecast": forecast}


@router.get("/{chart_id}/forecast/weekly", summary="Weekly personal forecast")
@limiter.limit(settings.rate_limit_anon)
async def get_weekly_forecast(
    request: Request,
    chart_id: str,
    week_start: str,
    week_end: str,
    db: Session = Depends(get_db),
):
    from backend.transit.engine import calculate_transits
    from backend.transit.forecast_prompt import build_weekly_forecast_prompt, parse_forecast_response

    chart = db.query(NatalChart).filter(NatalChart.id == chart_id).first()
    if not chart:
        raise HTTPException(status_code=404, detail="Chart not found")

    try:
        from_dt = date_type.fromisoformat(week_start)
        to_dt   = date_type.fromisoformat(week_end)
    except ValueError:
        raise HTTPException(status_code=422, detail="Формат даты: YYYY-MM-DD")

    events = calculate_transits(natal_planets=chart.planets, from_date=from_dt, to_date=to_dt)
    events_dicts = [
        {
            "transit_planet": e.transit_planet, "natal_planet": e.natal_planet,
            "aspect_type": e.aspect_type, "transit_sign": e.transit_sign,
            "peak_date": e.peak_date, "start_date": e.start_date,
            "end_date": e.end_date, "peak_orb": e.peak_orb,
        }
        for e in events
    ]
    natal_profile = {
        "planets": chart.planets, "houses": chart.houses,
        "ascendant": chart.ascendant, "midheaven": chart.midheaven, "time_unknown": chart.time_unknown,
    }
    prompt = build_weekly_forecast_prompt(
        week_start=week_start, week_end=week_end,
        transit_events=events_dicts, natal_profile=natal_profile,
    )
    raw = await _call_ai(prompt, max_tokens=2500)
    if not raw:
        raise HTTPException(status_code=503, detail="AI forecast unavailable.")
    try:
        forecast = parse_forecast_response(raw)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Parse error: {e}")
    return {"week_start": week_start, "week_end": week_end, "forecast": forecast}


@router.get("/{chart_id}/forecast/monthly", summary="Monthly personal forecast (JSON via AI)")
@limiter.limit(settings.rate_limit_anon)
async def get_monthly_forecast(
    request: Request,
    chart_id: str,
    from_date: str,
    to_date: str,
    db: Session = Depends(get_db),
):
    from backend.transit.engine import calculate_transits
    from backend.transit.forecast_prompt import build_monthly_forecast_prompt, parse_forecast_response

    chart = db.query(NatalChart).filter(NatalChart.id == chart_id).first()
    if not chart:
        raise HTTPException(status_code=404, detail="Chart not found")

    try:
        from_dt = date_type.fromisoformat(from_date)
        to_dt   = date_type.fromisoformat(to_date)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid date format.")

    events = calculate_transits(natal_planets=chart.planets, from_date=from_dt, to_date=to_dt)
    events_dicts = [
        {
            "transit_planet": e.transit_planet, "natal_planet": e.natal_planet,
            "aspect_type": e.aspect_type,
            "peak_orb":   getattr(e, "peak_orb", getattr(e, "orb", 0)),
            "transit_sign": getattr(e, "transit_sign", ""),
            "start_date": getattr(e, "start_date", getattr(e, "date", from_date)),
            "peak_date":  getattr(e, "peak_date",  getattr(e, "date", from_date)),
            "end_date":   getattr(e, "end_date",   getattr(e, "date", to_date)),
            "exact_date": getattr(e, "exact_date", None),
        }
        for e in events
    ]
    natal_profile = {
        "planets": chart.planets, "houses": chart.houses,
        "ascendant": chart.ascendant, "midheaven": chart.midheaven,
    }
    prompt = build_monthly_forecast_prompt(
        transit_events=events_dicts, natal_profile=natal_profile,
        from_date=from_date, to_date=to_date,
    )
    raw = await _call_ai(prompt, max_tokens=3000, timeout=90)
    if not raw:
        raise HTTPException(status_code=503, detail="AI forecast unavailable.")
    try:
        forecast = parse_forecast_response(raw)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse forecast: {e}")
    return {"from_date": from_date, "to_date": to_date, "forecast": forecast}


# ── Internal AI helper ────────────────────────────────────────────────────────

async def _call_ai(prompt: str, max_tokens: int = 2000, timeout: int = 60) -> str:
    """Try Anthropic then OpenAI; return raw text or empty string."""
    raw = ""
    if os.getenv("ANTHROPIC_API_KEY"):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": os.getenv("ANTHROPIC_API_KEY"),
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={"model": "claude-sonnet-4-20250514", "max_tokens": max_tokens, "messages": [{"role": "user", "content": prompt}]},
                )
                raw = resp.json()["content"][0]["text"]
        except Exception as e:
            logger.warning("Anthropic forecast failed: %s", e)

    if not raw and os.getenv("OPENAI_API_KEY"):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}", "Content-Type": "application/json"},
                    json={"model": "gpt-4o", "messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens, "response_format": {"type": "json_object"}},
                )
                raw = resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            logger.warning("OpenAI forecast failed: %s", e)

    return raw
