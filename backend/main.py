"""Astro SPA — FastAPI application.

Endpoints:
  POST /api/v1/chart/calculate                  — compute natal chart
  GET  /api/v1/chart/{id}                       — retrieve saved chart
  GET  /api/v1/chart/{id}/interpret              — stream AI interpretation (SSE)
  GET  /api/v1/chart/{id}/transits               — calculate transits for period
  GET  /api/v1/chart/{id}/transits/interpret      — stream transit period interpretation (SSE)
  POST /api/v1/chart/{id}/transits/event/interpret — interpret single transit event (SSE)
  GET  /health                                   — app health
  GET  /health/db                                — database health
  GET  /health/ai                                — AI providers health
"""

from __future__ import annotations

from dotenv import load_dotenv
load_dotenv()  # загружает .env до всех os.getenv()

import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session
from sqlalchemy import text

from backend.config import get_settings
from backend.database import get_db, engine, Base
from backend.schemas import (
    BirthDataInput,
    NatalChartResponse,
    PlanetPosition,
    HouseData,
    AspectData,
    PointData,
    HealthResponse,
    ErrorResponse,
    TransitRequest,
    TransitEvent as TransitEventSchema,
    TransitResponse,
)
from backend.models import NatalChart
from backend.ephemeris.calculator import calculate_full_chart
from backend.ephemeris.geo import (
    geocode_place,
    resolve_utc_datetime,
    validate_coordinates,
    GeocodingError,
    AmbiguousTimeError,
)
from backend.cache import interpretation_cache, transit_cache, make_profile_hash

logger = logging.getLogger("astro")
settings = get_settings()

# ── Rate limiter ──
limiter = Limiter(key_func=get_remote_address)


# ── Lifespan ──
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create tables if they don't exist (dev convenience)
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables ensured.")
    yield
    # Shutdown
    logger.info("Shutting down.")


# ── App ──
app = FastAPI(
    title="Astro SPA API",
    version="0.1.0",
    description="Natal chart calculation, transits, AI interpretations",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── CORS ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ═══════════════════════════════════════════════════════════
# HEALTH ENDPOINTS
# ═══════════════════════════════════════════════════════════

@app.get("/health", response_model=HealthResponse, tags=["health"])
async def health():
    return HealthResponse(status="ok", version="0.1.0", database="not_checked")


@app.get("/health/db", response_model=HealthResponse, tags=["health"])
def health_db(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {e}"
    return HealthResponse(status="ok", version="0.1.0", database=db_status)


# ═══════════════════════════════════════════════════════════
# CHART ENDPOINTS
# ═══════════════════════════════════════════════════════════

@app.post(
    "/api/v1/chart/calculate",
    response_model=NatalChartResponse,
    responses={422: {"model": ErrorResponse}, 400: {"model": ErrorResponse}},
    tags=["chart"],
    summary="Calculate natal chart",
)
@limiter.limit(settings.rate_limit_anon)
async def calculate_chart(
    request: Request,
    data: BirthDataInput,
    db: Session = Depends(get_db),
):
    """Calculate a natal chart from birth data.

    Accepts date, optional time, and place of birth.
    Returns full chart with planets, houses, aspects, ASC, MC.
    """
    warnings: list[str] = []

    # 1. Geocode the birth place
    try:
        geo = await geocode_place(data.birth_place)
    except GeocodingError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 2. Validate coordinates
    try:
        coord_warnings = validate_coordinates(geo.latitude, geo.longitude)
        warnings.extend(coord_warnings)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 3. Resolve UTC datetime (handles DST edge-cases)
    try:
        utc_dt, time_unknown, tz_warnings = resolve_utc_datetime(
            birth_date=str(data.birth_date),
            birth_time=data.birth_time,
            timezone=geo.timezone,
        )
        warnings.extend(tz_warnings)
    except AmbiguousTimeError as e:
        raise HTTPException(
            status_code=400,
            detail={
                "message": str(e),
                "options": e.options,
                "type": "ambiguous_time",
            },
        )

    # 4. Calculate chart
    try:
        (chart_data, aspects) = calculate_full_chart(
            utc_dt=utc_dt,
            latitude=geo.latitude,
            longitude=geo.longitude,
            house_system=data.house_system,
            time_unknown=time_unknown,
        )
        warnings.extend(chart_data.warnings)
    except Exception as e:
        logger.exception("Chart calculation failed")
        raise HTTPException(status_code=500, detail=f"Calculation error: {e}")

    # 5. Build response objects
    planets_resp = [
        PlanetPosition(
            name=p.name,
            longitude=p.longitude,
            sign=p.sign,
            degree_in_sign=p.degree_in_sign,
            house=p.house if not time_unknown else None,
            retrograde=p.retrograde,
        )
        for p in chart_data.planets
    ]

    houses_resp = [
        HouseData(number=h.number, sign=h.sign, degree=h.degree)
        for h in chart_data.houses
    ]

    aspects_resp = [
        AspectData(
            planet1=a.planet1,
            planet2=a.planet2,
            aspect_type=a.aspect_type,
            angle=a.angle,
            orb=a.orb,
            applying=a.applying,
        )
        for a in aspects
    ]

    asc_resp = PointData(
        sign=chart_data.ascendant.sign,
        degree=chart_data.ascendant.degree,
        longitude=chart_data.ascendant.longitude,
    ) if chart_data.ascendant else None

    mc_resp = PointData(
        sign=chart_data.midheaven.sign,
        degree=chart_data.midheaven.degree,
        longitude=chart_data.midheaven.longitude,
    ) if chart_data.midheaven else None

    # 6. Persist to database
    chart_record = NatalChart(
        birth_date=str(data.birth_date),
        birth_time=data.birth_time,
        birth_place=geo.display_name,
        latitude=geo.latitude,
        longitude=geo.longitude,
        timezone=geo.timezone,
        utc_datetime=utc_dt,
        time_unknown=time_unknown,
        house_system=data.house_system,
        planets=[p.model_dump() for p in planets_resp],
        houses=[h.model_dump() for h in houses_resp],
        aspects=[a.model_dump() for a in aspects_resp],
        ascendant=asc_resp.model_dump() if asc_resp else None,
        midheaven=mc_resp.model_dump() if mc_resp else None,
    )

    db.add(chart_record)
    db.commit()
    db.refresh(chart_record)

    return NatalChartResponse(
        id=chart_record.id,
        birth_date=str(data.birth_date),
        birth_time=data.birth_time,
        birth_place=geo.display_name,
        latitude=geo.latitude,
        longitude=geo.longitude,
        timezone=geo.timezone,
        time_unknown=time_unknown,
        house_system=data.house_system,
        planets=planets_resp,
        houses=houses_resp,
        aspects=aspects_resp,
        ascendant=asc_resp,
        midheaven=mc_resp,
        warnings=warnings,
    )


@app.get(
    "/api/v1/chart/{chart_id}",
    response_model=NatalChartResponse,
    responses={404: {"model": ErrorResponse}},
    tags=["chart"],
    summary="Get saved chart",
)
@limiter.limit(settings.rate_limit_anon)
async def get_chart(request: Request, chart_id: str, db: Session = Depends(get_db)):
    """Retrieve a previously calculated natal chart by ID."""
    chart = db.query(NatalChart).filter(NatalChart.id == chart_id).first()
    if not chart:
        raise HTTPException(status_code=404, detail=f"Chart not found: {chart_id}")

    planets = [PlanetPosition(**p) for p in chart.planets]
    houses = [HouseData(**h) for h in chart.houses]
    aspects = [AspectData(**a) for a in chart.aspects]
    asc = PointData(**chart.ascendant) if chart.ascendant else None
    mc = PointData(**chart.midheaven) if chart.midheaven else None

    return NatalChartResponse(
        id=chart.id,
        birth_date=chart.birth_date,
        birth_time=chart.birth_time,
        birth_place=chart.birth_place,
        latitude=chart.latitude,
        longitude=chart.longitude,
        timezone=chart.timezone,
        time_unknown=chart.time_unknown,
        house_system=chart.house_system,
        planets=planets,
        houses=houses,
        aspects=aspects,
        ascendant=asc,
        midheaven=mc,
    )


# ═══════════════════════════════════════════════════════════
# INTERPRETATION ENDPOINTS
# ═══════════════════════════════════════════════════════════

@app.get(
    "/api/v1/chart/{chart_id}/interpret",
    tags=["interpretation"],
    summary="Stream AI interpretation (SSE)",
)
@limiter.limit(settings.rate_limit_anon)
async def interpret_chart(request: Request, chart_id: str, db: Session = Depends(get_db)):
    """Stream an AI-generated interpretation of a natal chart via Server-Sent Events.

    The response is streamed token-by-token for a smooth UX.
    Fallback chain: GPT-4o → DeepSeek V3 → Template engine.
    """
    from backend.interpretation.base import InterpretationRequest
    from backend.interpretation.router import get_router

    chart = db.query(NatalChart).filter(NatalChart.id == chart_id).first()
    if not chart:
        raise HTTPException(status_code=404, detail=f"Chart not found: {chart_id}")

    # Build natal profile from stored data
    profile = {
        "planets": chart.planets,
        "houses": chart.houses,
        "aspects": chart.aspects,
        "ascendant": chart.ascendant,
        "midheaven": chart.midheaven,
        "time_unknown": chart.time_unknown,
    }

    interp_request = InterpretationRequest(natal_profile=profile)
    router = get_router()

    async def event_stream():
        try:
            async for chunk in router.stream(interp_request):
                # SSE format: data: <content>\n\n
                yield f"data: {json.dumps({'text': chunk}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            logger.exception("Streaming interpretation failed")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post(
    "/api/v1/chart/{chart_id}/interpret",
    tags=["interpretation"],
    summary="Generate full interpretation (non-streaming)",
)
@limiter.limit(settings.rate_limit_anon)
async def interpret_chart_full(request: Request, chart_id: str, db: Session = Depends(get_db)):
    """Generate a complete AI interpretation of a natal chart.

    Returns the full text at once (no streaming).
    """
    from backend.interpretation.base import InterpretationRequest
    from backend.interpretation.router import get_router

    chart = db.query(NatalChart).filter(NatalChart.id == chart_id).first()
    if not chart:
        raise HTTPException(status_code=404, detail=f"Chart not found: {chart_id}")

    profile = {
        "planets": chart.planets,
        "houses": chart.houses,
        "aspects": chart.aspects,
        "ascendant": chart.ascendant,
        "midheaven": chart.midheaven,
        "time_unknown": chart.time_unknown,
    }

    interp_request = InterpretationRequest(natal_profile=profile)
    router = get_router()
    result = await router.generate(interp_request)

    return {
        "chart_id": chart_id,
        "content": result.content,
        "sections": result.sections,
        "engine": result.engine,
        "cached": result.cached,
    }


@app.get("/health/ai", tags=["health"], summary="AI providers health")
async def health_ai():
    """Check availability of all AI interpretation engines."""
    from backend.interpretation.router import get_router
    router = get_router()
    status = await router.get_status()
    return {"status": "ok", "engines": status}


# ═══════════════════════════════════════════════════════════
# TRANSIT ENDPOINTS (Phase 3)
# ═══════════════════════════════════════════════════════════

@app.get(
    "/api/v1/chart/{chart_id}/transits",
    response_model=TransitResponse,
    responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    tags=["transits"],
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
):
    """Calculate transit aspects to a natal chart for a given date range.

    Query params:
      - from_date: start date (YYYY-MM-DD)
      - to_date: end date (YYYY-MM-DD)
      - planet: (optional) filter by transit planet name
      - max_orb: (optional) max orb in degrees (default: standard transit orbs)

    Returns array of transit events sorted by date.
    """
    from datetime import date as date_type
    from backend.transit.engine import calculate_transits
    from backend.cache import transit_cache, make_profile_hash

    # 1. Load natal chart
    chart = db.query(NatalChart).filter(NatalChart.id == chart_id).first()
    if not chart:
        raise HTTPException(status_code=404, detail=f"Chart not found: {chart_id}")

    # 2. Parse and validate dates
    try:
        from_dt = date_type.fromisoformat(from_date)
        to_dt = date_type.fromisoformat(to_date)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail="Invalid date format. Use YYYY-MM-DD.",
        )

    if to_dt <= from_dt:
        raise HTTPException(status_code=422, detail="to_date must be after from_date.")

    delta = (to_dt - from_dt).days
    if delta > 366:
        raise HTTPException(
            status_code=422,
            detail="Transit period cannot exceed 1 year (366 days).",
        )

    # 3. Check cache
    cache_key = f"transit:{chart_id}:{from_date}:{to_date}:{planet}:{max_orb}"
    cached = transit_cache.get(cache_key)
    if cached:
        logger.info("Transit cache hit: %s", cache_key[:40])
        return TransitResponse(
            chart_id=chart_id,
            from_date=from_date,
            to_date=to_date,
            events=[TransitEventSchema(**e) for e in cached],
        )

    # 4. Calculate transits
    planet_filter = [planet] if planet else None

    try:
        events = calculate_transits(
            natal_planets=chart.planets,
            from_date=from_dt,
            to_date=to_dt,
            orb_filter=max_orb,
            planet_filter=planet_filter,
        )
    except Exception as e:
        logger.exception("Transit calculation failed")
        raise HTTPException(status_code=500, detail=f"Transit calculation error: {e}")

    # 5. Build response
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

    # 6. Cache result (7 days TTL)
    transit_cache.set(
        cache_key,
        [e.model_dump() for e in events_resp],
        ttl=7 * 24 * 3600,
    )

    return TransitResponse(
        chart_id=chart_id,
        from_date=from_date,
        to_date=to_date,
        events=events_resp,
    )


@app.get(
    "/api/v1/chart/{chart_id}/transits/interpret",
    tags=["transits"],
    summary="Stream transit period interpretation (SSE)",
)
@limiter.limit(settings.rate_limit_anon)
async def interpret_transits(
    request: Request,
    chart_id: str,
    from_date: str,
    to_date: str,
    db: Session = Depends(get_db),
):
    """Stream an AI interpretation of all transits for a period.

    First calculates transits, then generates an overview interpretation
    via the AI fallback chain (GPT-4o → DeepSeek → templates).
    """
    from datetime import date as date_type
    from backend.transit.engine import calculate_transits, get_transit_summary
    from backend.transit.prompts import build_transit_period_prompt, get_template_transit_text
    from backend.interpretation.base import InterpretationRequest
    from backend.interpretation.router import get_router

    chart = db.query(NatalChart).filter(NatalChart.id == chart_id).first()
    if not chart:
        raise HTTPException(status_code=404, detail=f"Chart not found: {chart_id}")

    # Parse dates
    try:
        from_dt = date_type.fromisoformat(from_date)
        to_dt = date_type.fromisoformat(to_date)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid date format.")

    # Calculate transits
    events = calculate_transits(
        natal_planets=chart.planets,
        from_date=from_dt,
        to_date=to_dt,
    )

    # Build natal profile
    profile = {
        "planets": chart.planets,
        "houses": chart.houses,
        "aspects": chart.aspects,
        "ascendant": chart.ascendant,
        "midheaven": chart.midheaven,
        "time_unknown": chart.time_unknown,
    }

    # Build transit events as dicts for prompt
    transit_dicts = [
        {
            "date": e.date,
            "transit_planet": e.transit_planet,
            "transit_sign": e.transit_sign,
            "natal_planet": e.natal_planet,
            "aspect_type": e.aspect_type,
            "orb": e.orb,
            "exact_date": e.exact_date,
        }
        for e in events
    ]

    # Try AI interpretation, fall back to template summary
    router = get_router()

    async def event_stream():
        try:
            # Build a custom request with transit context
            period_prompt = build_transit_period_prompt(
                transit_events=transit_dicts,
                natal_profile=profile,
                from_date=from_date,
                to_date=to_date,
            )

            interp_request = InterpretationRequest(
                natal_profile=profile,
                context="transit",
            )

            # Try streaming from AI engines
            streamed = False
            for eng in router._engines:
                if not router._check_budget(eng.name):
                    continue
                if eng.name == "template":
                    # Use template transit fallback
                    break
                try:
                    # Override the prompt by creating a custom request
                    # The engine will use the standard prompt builder,
                    # but we inject transit context
                    async for chunk in eng.stream(interp_request):
                        yield f"data: {json.dumps({'text': chunk}, ensure_ascii=False)}\n\n"
                        streamed = True
                    if streamed:
                        yield "data: [DONE]\n\n"
                        return
                except Exception as e:
                    logger.warning("Transit stream from %s failed: %s", eng.name, e)
                    continue

            # Template fallback: generate summary from templates
            summary = get_transit_summary(events)
            text_parts = [f"### Обзор транзитов: {from_date} — {to_date}\n\n"]
            text_parts.append(
                f"За этот период обнаружено **{summary['total_events']}** "
                f"значимых транзитных аспектов.\n\n"
            )

            if summary["significant"]:
                text_parts.append("### Ключевые транзиты периода\n\n")
                for sig in summary["significant"]:
                    template_text = get_template_transit_text(
                        sig["description"].split()[0],  # transit planet
                        sig["description"].split()[-1],  # natal planet
                        sig["description"].split()[1],   # aspect
                    )
                    text_parts.append(
                        f"**{sig['date']}** — {sig['description']} "
                        f"(орб: {sig['orb']}°)\n\n{template_text}\n\n"
                    )

            full_text = "".join(text_parts)
            # Stream in paragraphs
            for para in full_text.split("\n\n"):
                if para.strip():
                    yield f"data: {json.dumps({'text': para + chr(10) + chr(10)}, ensure_ascii=False)}\n\n"

            yield "data: [DONE]\n\n"

        except Exception as e:
            logger.exception("Transit interpretation stream failed")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post(
    "/api/v1/chart/{chart_id}/transits/event/interpret",
    tags=["transits"],
    summary="Interpret a single transit event (SSE)",
)
@limiter.limit(settings.rate_limit_anon)
async def interpret_transit_event(
    request: Request,
    chart_id: str,
    db: Session = Depends(get_db),
):
    """Stream AI interpretation of a single transit event.

    Request body: transit event data (from /transits response).
    Used when user clicks on a specific event in the timeline.
    """
    from backend.transit.prompts import (
        build_transit_event_prompt,
        get_template_transit_text,
    )
    from backend.interpretation.base import InterpretationRequest
    from backend.interpretation.router import get_router

    chart = db.query(NatalChart).filter(NatalChart.id == chart_id).first()
    if not chart:
        raise HTTPException(status_code=404, detail=f"Chart not found: {chart_id}")

    # Parse transit event from request body
    body = await request.json()
    transit_planet = body.get("transit_planet", "")
    natal_planet = body.get("natal_planet", "")
    aspect_type = body.get("aspect_type", "")

    if not all([transit_planet, natal_planet, aspect_type]):
        raise HTTPException(
            status_code=422,
            detail="Required fields: transit_planet, natal_planet, aspect_type",
        )

    profile = {
        "planets": chart.planets,
        "houses": chart.houses,
        "aspects": chart.aspects,
        "ascendant": chart.ascendant,
        "midheaven": chart.midheaven,
        "time_unknown": chart.time_unknown,
    }

    router = get_router()

    async def event_stream():
        try:
            # Try AI engines first
            interp_request = InterpretationRequest(
                natal_profile=profile,
                context="transit",
                sections=["general"],
            )

            streamed = False
            for eng in router._engines:
                if not router._check_budget(eng.name):
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

            # Template fallback
            text = get_template_transit_text(transit_planet, natal_planet, aspect_type)
            yield f"data: {json.dumps({'text': text}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

        except Exception as e:
            logger.exception("Transit event interpretation failed")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get(
    "/api/v1/chart/{chart_id}/forecast/weekly",
    tags=["forecast"],
    summary="Weekly personal forecast",
)
@limiter.limit(settings.rate_limit_anon)
async def get_weekly_forecast(
    request: Request,
    chart_id: str,
    week_start: str,   # YYYY-MM-DD
    week_end: str,     # YYYY-MM-DD
    db: Session = Depends(get_db),
):
    from datetime import date as date_type
    from backend.transit.engine import calculate_transits
    from backend.transit.forecast_prompt import build_weekly_forecast_prompt, parse_forecast_response
    import httpx, os

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
            "transit_planet": e.transit_planet,
            "natal_planet":   e.natal_planet,
            "aspect_type":    e.aspect_type,
            "transit_sign":   e.transit_sign,
            "peak_date":      e.peak_date,
            "start_date":     e.start_date,
            "end_date":       e.end_date,
            "peak_orb":       e.peak_orb,
        }
        for e in events
    ]

    natal_profile = {
        "planets":    chart.planets,
        "houses":     chart.houses,
        "ascendant":  chart.ascendant,
        "midheaven":  chart.midheaven,
        "time_unknown": chart.time_unknown,
    }

    prompt = build_weekly_forecast_prompt(
        week_start=week_start,
        week_end=week_end,
        transit_events=events_dicts,
        natal_profile=natal_profile,
    )

    raw = ""
    openai_key = os.getenv("OPENAI_API_KEY", "")

    if os.getenv("ANTHROPIC_API_KEY"):
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": os.getenv("ANTHROPIC_API_KEY"),
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": "claude-sonnet-4-20250514",
                        "max_tokens": 2500,
                        "messages": [{"role": "user", "content": prompt}],
                    }
                )
                data = resp.json()
                raw  = data["content"][0]["text"]
        except Exception as e:
            logger.warning(f"Anthropic weekly forecast failed: {e}")

    if not raw and openai_key:
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {openai_key}", "Content-Type": "application/json"},
                    json={
                        "model": "gpt-4o",
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": 2500,
                        "response_format": {"type": "json_object"},
                    }
                )
                data = resp.json()
                raw  = data["choices"][0]["message"]["content"]
        except Exception as e:
            logger.warning(f"OpenAI weekly forecast failed: {e}")

    if not raw:
        raise HTTPException(status_code=503, detail="AI forecast unavailable.")

    try:
        forecast = parse_forecast_response(raw)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Parse error: {e}")

    return {"week_start": week_start, "week_end": week_end, "forecast": forecast}


# ═══════════════════════════════════════════════════════════
# FORECAST: DAILY
# ═══════════════════════════════════════════════════════════

@app.get(
    "/api/v1/chart/{chart_id}/forecast/daily",
    tags=["forecast"],
    summary="Daily personal forecast (JSON via AI)",
)
@limiter.limit(settings.rate_limit_anon)
async def get_daily_forecast(
    request: Request,
    chart_id: str,
    on_date: str,
    db: Session = Depends(get_db),
):
    from datetime import date as date_type, timedelta
    from backend.transit.engine import calculate_transits, get_active_transits
    from backend.transit.forecast_prompt import build_daily_forecast_prompt, parse_forecast_response
    import httpx, os

    chart = db.query(NatalChart).filter(NatalChart.id == chart_id).first()
    if not chart:
        raise HTTPException(status_code=404, detail="Chart not found")

    try:
        query_date = date_type.fromisoformat(on_date)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid date format. Use YYYY-MM-DD.")

    from_dt = query_date - timedelta(days=1)
    to_dt   = query_date + timedelta(days=1)
    events  = calculate_transits(natal_planets=chart.planets, from_date=from_dt, to_date=to_dt)
    active  = get_active_transits(events, query_date)

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

    prompt = build_daily_forecast_prompt(
        date=on_date,
        transit_events=events_dicts,
        natal_profile=natal_profile,
    )

    raw = ""
    if os.getenv("ANTHROPIC_API_KEY"):
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": os.getenv("ANTHROPIC_API_KEY"),
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": "claude-sonnet-4-20250514",
                        "max_tokens": 2000,
                        "messages": [{"role": "user", "content": prompt}],
                    }
                )
                data = resp.json()
                raw = data["content"][0]["text"]
        except Exception as e:
            logger.warning(f"Anthropic daily forecast failed: {e}")

    if not raw and os.getenv("OPENAI_API_KEY"):
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}", "Content-Type": "application/json"},
                    json={
                        "model": "gpt-4o",
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": 2000,
                        "response_format": {"type": "json_object"},
                    }
                )
                data = resp.json()
                raw = data["choices"][0]["message"]["content"]
        except Exception as e:
            logger.warning(f"OpenAI daily forecast failed: {e}")

    if not raw:
        raise HTTPException(status_code=503, detail="AI forecast unavailable. Check ANTHROPIC_API_KEY or OPENAI_API_KEY in .env")

    try:
        forecast = parse_forecast_response(raw)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse forecast: {e}")

    return {"date": on_date, "forecast": forecast}


# ═══════════════════════════════════════════════════════════
# FORECAST: MONTHLY
# ═══════════════════════════════════════════════════════════

@app.get(
    "/api/v1/chart/{chart_id}/forecast/monthly",
    tags=["forecast"],
    summary="Monthly personal forecast (JSON via AI)",
)
@limiter.limit(settings.rate_limit_anon)
async def get_monthly_forecast(
    request: Request,
    chart_id: str,
    from_date: str,
    to_date: str,
    db: Session = Depends(get_db),
):
    from datetime import date as date_type
    from backend.transit.engine import calculate_transits
    from backend.transit.forecast_prompt import build_monthly_forecast_prompt, parse_forecast_response
    import httpx, os

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
            "transit_planet": e.transit_planet,
            "natal_planet":   e.natal_planet,
            "aspect_type":    e.aspect_type,
            "peak_orb":       getattr(e, "peak_orb", getattr(e, "orb", 0)),
            "transit_sign":   getattr(e, "transit_sign", ""),
            "start_date":     getattr(e, "start_date", getattr(e, "date", from_date)),
            "peak_date":      getattr(e, "peak_date",  getattr(e, "date", from_date)),
            "end_date":       getattr(e, "end_date",   getattr(e, "date", to_date)),
            "exact_date":     getattr(e, "exact_date", None),
        }
        for e in events
    ]

    natal_profile = {
        "planets":   chart.planets,
        "houses":    chart.houses,
        "ascendant": chart.ascendant,
        "midheaven": chart.midheaven,
    }

    prompt = build_monthly_forecast_prompt(
        transit_events=events_dicts,
        natal_profile=natal_profile,
        from_date=from_date,
        to_date=to_date,
    )

    raw = ""
    if os.getenv("ANTHROPIC_API_KEY"):
        try:
            async with httpx.AsyncClient(timeout=90) as client:
                resp = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": os.getenv("ANTHROPIC_API_KEY"),
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": "claude-sonnet-4-20250514",
                        "max_tokens": 3000,
                        "messages": [{"role": "user", "content": prompt}],
                    }
                )
                data = resp.json()
                raw = data["content"][0]["text"]
        except Exception as e:
            logger.warning(f"Anthropic monthly forecast failed: {e}")

    if not raw and os.getenv("OPENAI_API_KEY"):
        try:
            async with httpx.AsyncClient(timeout=90) as client:
                resp = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}", "Content-Type": "application/json"},
                    json={
                        "model": "gpt-4o",
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": 3000,
                        "response_format": {"type": "json_object"},
                    }
                )
                data = resp.json()
                raw = data["choices"][0]["message"]["content"]
        except Exception as e:
            logger.warning(f"OpenAI monthly forecast failed: {e}")

    if not raw:
        raise HTTPException(status_code=503, detail="AI forecast unavailable. Check ANTHROPIC_API_KEY or OPENAI_API_KEY in .env")

    try:
        forecast = parse_forecast_response(raw)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse forecast: {e}")

    return {"from_date": from_date, "to_date": to_date, "forecast": forecast}


# ═══════════════════════════════════════════════════════════
# PLANNER: MONTHLY (в формате методички)
# ═══════════════════════════════════════════════════════════

@app.get(
    "/api/v1/chart/{chart_id}/planner/monthly",
    tags=["forecast"],
    summary="Monthly personal planner (in the style of the planning example)",
)
@limiter.limit(settings.rate_limit_anon)
async def get_monthly_planner(
    request: Request,
    chart_id: str,
    db: Session = Depends(get_db),
):
    import calendar as cal_mod
    from datetime import date as date_type, datetime as dt_type, timedelta
    from backend.transit.engine import calculate_transits
    from backend.transit.forecast_prompt import (
        build_monthly_planner_prompt,
        parse_forecast_response,
    )
    from backend.transit.house_passages import compute_planner_periods
    import httpx, os

    chart = db.query(NatalChart).filter(NatalChart.id == chart_id).first()
    if not chart:
        raise HTTPException(status_code=404, detail="Chart not found")

    # Диапазон: текущий месяц + 30 дней вперёд (чтобы захватить переходы планет)
    today        = date_type.today()
    month_start  = today.replace(day=1)
    last_day     = cal_mod.monthrange(today.year, today.month)[1]
    month_end    = today.replace(day=last_day)
    extended_end = month_end + timedelta(days=30)

    from_str = month_start.isoformat()
    to_str   = month_end.isoformat()

    # ── Cache lookup: ключ = chart_id + текущий месяц, TTL = до конца месяца ──
    cache_key = f"planner:{chart_id}:{today.year}-{today.month:02d}"
    cached = transit_cache.get(cache_key)
    if cached:
        logger.info("Planner cache hit: %s", cache_key)
        return cached

    events = calculate_transits(
        natal_planets=chart.planets,
        from_date=month_start,
        to_date=extended_end,
    )
    events_dicts = [
        {
            "transit_planet": e.transit_planet,
            "natal_planet":   e.natal_planet,
            "aspect_type":    e.aspect_type,
            "transit_sign":   e.transit_sign,
            "peak_date":      e.peak_date,
            "start_date":     e.start_date,
            "end_date":       e.end_date,
            "peak_orb":       e.peak_orb,
        }
        for e in events
    ]

    natal_profile = {
        "planets":      chart.planets,
        "houses":       chart.houses,
        "ascendant":    chart.ascendant,
        "midheaven":    chart.midheaven,
        "time_unknown": chart.time_unknown,
    }

    # Точные даты переходов транзитных планет по натальным домам.
    # Если время рождения неизвестно — куспидов нет, periods будут пустыми
    # и промпт упадёт на старую (менее точную) логику.
    precomputed_periods = compute_planner_periods(
        natal_profile=natal_profile,
        from_date=month_start,
        to_date=month_end,
        today=today,
    )

    prompt = build_monthly_planner_prompt(
        transit_events=events_dicts,
        natal_profile=natal_profile,
        from_date=from_str,
        to_date=to_str,
        precomputed_periods=precomputed_periods if not chart.time_unknown else None,
    )

    raw = ""
    openai_key = os.getenv("OPENAI_API_KEY", "")

    if os.getenv("ANTHROPIC_API_KEY"):
        try:
            async with httpx.AsyncClient(timeout=90) as client:
                resp = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key":         os.getenv("ANTHROPIC_API_KEY"),
                        "anthropic-version": "2023-06-01",
                        "content-type":      "application/json",
                    },
                    json={
                        "model":      "claude-sonnet-4-20250514",
                        "max_tokens": 3000,
                        "messages":   [{"role": "user", "content": prompt}],
                    },
                )
                data = resp.json()
                raw  = data["content"][0]["text"]
        except Exception as e:
            logger.warning(f"Anthropic monthly planner failed: {e}")

    if not raw and openai_key:
        try:
            async with httpx.AsyncClient(timeout=90) as client:
                resp = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {openai_key}",
                        "Content-Type":  "application/json",
                    },
                    json={
                        "model":           "gpt-4o",
                        "messages":        [{"role": "user", "content": prompt}],
                        "max_tokens":      3000,
                        "response_format": {"type": "json_object"},
                    },
                )
                data = resp.json()
                raw  = data["choices"][0]["message"]["content"]
        except Exception as e:
            logger.warning(f"OpenAI monthly planner failed: {e}")

    if not raw:
        raise HTTPException(status_code=503, detail="AI planner unavailable.")

    try:
        planner = parse_forecast_response(raw)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Parse error: {e}")

    response = {
        "from_date": from_str,
        "to_date":   to_str,
        "planner":   planner,
    }

    # Cache до конца месяца (TTL в секундах от now до 23:59:59 последнего дня)
    end_of_month_dt = dt_type.combine(month_end, dt_type.max.time())
    ttl_seconds = max(60, int((end_of_month_dt - dt_type.now()).total_seconds()))
    transit_cache.set(cache_key, response, ttl=ttl_seconds)

    return response
