"""Transits router — Transit Engine endpoints."""

from __future__ import annotations

import json
import logging
from datetime import date as date_type

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.database import get_db
from backend.schemas import ErrorResponse, TransitEvent as TransitEventSchema, TransitResponse
from backend.models import NatalChart, User
from backend.cache import transit_cache
from backend.auth.dependencies import get_current_user_optional
from backend.auth.rate_limits import tier_limiter
from backend.limiter import limiter

logger = logging.getLogger("astro")
settings = get_settings()

router = APIRouter(prefix="/api/v1/chart", tags=["transits"])


def _parse_date(value: str, field: str = "date") -> date_type:
    try:
        return date_type.fromisoformat(value)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid {field} format. Use YYYY-MM-DD.")


def _load_chart(chart_id: str, db: Session) -> NatalChart:
    chart = db.query(NatalChart).filter(NatalChart.id == chart_id).first()
    if not chart:
        raise HTTPException(status_code=404, detail=f"Chart not found: {chart_id}")
    return chart


@router.get(
    "/{chart_id}/transits",
    response_model=TransitResponse,
    responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    summary="Calculate transits for a period",
)
@limiter.limit(settings.rate_limit_anon)
async def get_transits(
    request: Request,
    chart_id: str,
    from_date: str,
    to_date: str,
    planet: str | None = None,
    max_orb: float | None = None,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    tier_limiter.check_transit_access(user)
    from backend.transit.engine import calculate_transits

    chart = _load_chart(chart_id, db)
    from_dt = _parse_date(from_date, "from_date")
    to_dt   = _parse_date(to_date, "to_date")

    if to_dt <= from_dt:
        raise HTTPException(status_code=422, detail="to_date must be after from_date.")
    if (to_dt - from_dt).days > 366:
        raise HTTPException(status_code=422, detail="Transit period cannot exceed 1 year (366 days).")

    cache_key = f"transit:{chart_id}:{from_date}:{to_date}:{planet}:{max_orb}"
    cached = transit_cache.get(cache_key)
    if cached:
        return TransitResponse(
            chart_id=chart_id, from_date=from_date, to_date=to_date,
            events=[TransitEventSchema(**e) for e in cached],
        )

    try:
        events = calculate_transits(
            natal_planets=chart.planets,
            from_date=from_dt,
            to_date=to_dt,
            orb_filter=max_orb,
            planet_filter=[planet] if planet else None,
        )
    except Exception as e:
        logger.exception("Transit calculation failed")
        raise HTTPException(status_code=500, detail=f"Transit calculation error: {e}")

    events_resp = [
        TransitEventSchema(
            start_date=getattr(e, "start_date", None) or getattr(e, "date", ""),
            peak_date=getattr(e, "peak_date", None) or getattr(e, "date", ""),
            end_date=getattr(e, "end_date", None) or getattr(e, "date", ""),
            transit_planet=e.transit_planet,
            transit_sign=getattr(e, "transit_sign", ""),
            natal_planet=e.natal_planet,
            natal_sign=getattr(e, "natal_sign", ""),
            aspect_type=e.aspect_type,
            peak_orb=getattr(e, "peak_orb", None) or getattr(e, "orb", 0.0),
            exact_date=getattr(e, "exact_date", None),
            applying=getattr(e, "applying", True),
        )
        for e in events
    ]

    transit_cache.set(cache_key, [e.model_dump() for e in events_resp], ttl=7 * 24 * 3600)

    return TransitResponse(chart_id=chart_id, from_date=from_date, to_date=to_date, events=events_resp)


@router.get("/{chart_id}/transits/positions", summary="Current transit planet positions for a given date")
async def get_transit_positions(
    chart_id: str,
    on_date: str,
    db: Session = Depends(get_db),
):
    from backend.transit.engine import get_planet_positions_for_date

    _load_chart(chart_id, db)
    query_date = _parse_date(on_date, "on_date")
    planets = get_planet_positions_for_date(query_date)
    return {"date": on_date, "planets": planets}


@router.get("/{chart_id}/transits/interpret", summary="Stream transit period interpretation (SSE)")
@limiter.limit(settings.rate_limit_anon)
async def interpret_transits(
    request: Request,
    chart_id: str,
    from_date: str,
    to_date: str,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    tier_limiter.check_transit_access(user)
    from backend.transit.engine import calculate_transits, get_transit_summary
    from backend.transit.prompts import build_transit_period_prompt, get_template_transit_text
    from backend.interpretation.base import InterpretationRequest
    from backend.interpretation.router import get_router

    chart = _load_chart(chart_id, db)
    from_dt = _parse_date(from_date, "from_date")
    to_dt   = _parse_date(to_date, "to_date")

    events = calculate_transits(natal_planets=chart.planets, from_date=from_dt, to_date=to_dt)
    profile = {
        "planets": chart.planets, "houses": chart.houses, "aspects": chart.aspects,
        "ascendant": chart.ascendant, "midheaven": chart.midheaven, "time_unknown": chart.time_unknown,
    }
    transit_dicts = [
        {
            "date": e.date, "transit_planet": e.transit_planet, "transit_sign": e.transit_sign,
            "natal_planet": e.natal_planet, "aspect_type": e.aspect_type,
            "orb": e.orb, "exact_date": e.exact_date,
        }
        for e in events
    ]

    ai_router = get_router()

    async def event_stream():
        try:
            interp_request = InterpretationRequest(natal_profile=profile, context="transit")
            streamed = False
            for eng in ai_router._engines:
                if not ai_router._check_budget(eng.name):
                    continue
                if eng.name == "template":
                    break
                try:
                    async for chunk in eng.stream(interp_request):
                        yield f"data: {json.dumps({'text': chunk}, ensure_ascii=False)}\n\n"
                        streamed = True
                    if streamed:
                        yield "data: [DONE]\n\n"
                        return
                except Exception as e:
                    logger.warning("Transit stream from %s failed: %s", eng.name, e)
                    continue

            # Template fallback
            summary = get_transit_summary(events)
            text_parts = [f"### Обзор транзитов: {from_date} — {to_date}\n\n"]
            text_parts.append(f"За этот период обнаружено **{summary['total_events']}** значимых транзитных аспектов.\n\n")
            if summary["significant"]:
                text_parts.append("### Ключевые транзиты периода\n\n")
                for sig in summary["significant"]:
                    parts = sig["description"].split()
                    template_text = get_template_transit_text(parts[0], parts[-1], parts[1])
                    text_parts.append(f"**{sig['date']}** — {sig['description']} (орб: {sig['orb']}°)\n\n{template_text}\n\n")

            for para in "".join(text_parts).split("\n\n"):
                if para.strip():
                    yield f"data: {json.dumps({'text': para + chr(10) + chr(10)}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

        except Exception as e:
            logger.exception("Transit interpretation stream failed")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.post("/{chart_id}/transits/event/interpret", summary="Interpret a single transit event (SSE)")
@limiter.limit(settings.rate_limit_anon)
async def interpret_transit_event(
    request: Request,
    chart_id: str,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    tier_limiter.check_transit_access(user)
    from backend.transit.prompts import get_template_transit_text
    from backend.interpretation.base import InterpretationRequest
    from backend.interpretation.router import get_router

    chart = _load_chart(chart_id, db)
    body = await request.json()
    transit_planet = body.get("transit_planet", "")
    natal_planet   = body.get("natal_planet", "")
    aspect_type    = body.get("aspect_type", "")

    if not all([transit_planet, natal_planet, aspect_type]):
        raise HTTPException(status_code=422, detail="Required fields: transit_planet, natal_planet, aspect_type")

    profile = {
        "planets": chart.planets, "houses": chart.houses, "aspects": chart.aspects,
        "ascendant": chart.ascendant, "midheaven": chart.midheaven, "time_unknown": chart.time_unknown,
    }
    ai_router = get_router()

    async def event_stream():
        try:
            interp_request = InterpretationRequest(natal_profile=profile, context="transit", sections=["general"])
            streamed = False
            for eng in ai_router._engines:
                if not ai_router._check_budget(eng.name):
                    continue
                if eng.name == "template":
                    break
                try:
                    async for chunk in eng.stream(interp_request):
                        yield f"data: {json.dumps({'text': chunk}, ensure_ascii=False)}\n\n"
                        streamed = True
                    if streamed:
                        yield "data: [DONE]\n\n"
                        return
                except Exception:
                    continue

            text = get_template_transit_text(transit_planet, natal_planet, aspect_type)
            yield f"data: {json.dumps({'text': text}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

        except Exception as e:
            logger.exception("Transit event interpretation failed")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )
