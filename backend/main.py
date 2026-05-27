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
from fastapi.responses import JSONResponse, StreamingResponse, Response
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
from backend.calendar.lunar_engine import get_monthly_calendar
from backend.auth.router import router as auth_router
from backend.profile.router import router as profile_router
from backend.profile.settings_router import router as settings_router
from backend.onboarding_router import router as onboarding_router
from backend.auth.dependencies import get_current_user_optional
from backend.auth.rate_limits import tier_limiter
from backend.models import User

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

# ── Routers ──
app.include_router(auth_router)
app.include_router(profile_router)
app.include_router(settings_router)
app.include_router(onboarding_router)


# ═══════════════════════════════════════════════════════════
# PROMETHEUS METRICS
# ═══════════════════════════════════════════════════════════

@app.get("/metrics", tags=["monitoring"], summary="Prometheus metrics endpoint")
def metrics():
    """Expose Prometheus metrics."""
    from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


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
async def interpret_chart(
    request: Request,
    chart_id: str,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    """Stream an AI-generated interpretation of a natal chart via Server-Sent Events.

    The response is streamed token-by-token for a smooth UX.
    Fallback chain: GPT-4o → DeepSeek V3 → Template engine.
    """
    tier_limiter.check_interpretation_limit(user)
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
async def interpret_chart_full(
    request: Request,
    chart_id: str,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    """Generate a complete AI interpretation of a natal chart.

    Returns the full text at once (no streaming).
    """
    tier_limiter.check_interpretation_limit(user)
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
    """Check availability of all AI providers and infrastructure services.
    
    Returns:
        - status: "ok" | "degraded" | "down"
        - services: detailed status for OpenAI, DeepSeek, Redis, PostgreSQL
    """
    from backend.health import check_all_services
    return await check_all_services()


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
    user: User | None = Depends(get_current_user_optional),
):
    """Calculate transit aspects to a natal chart for a given date range.

    Query params:
      - from_date: start date (YYYY-MM-DD)
      - to_date: end date (YYYY-MM-DD)
      - planet: (optional) filter by transit planet name
      - max_orb: (optional) max orb in degrees (default: standard transit orbs)

    Returns array of transit events sorted by date.
    """
    tier_limiter.check_transit_access(user)
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
    "/api/v1/chart/{chart_id}/transits/positions",
    tags=["transits"],
    summary="Current transit planet positions for a given date",
)
async def get_transit_positions(
    chart_id: str,
    on_date: str,
    db: Session = Depends(get_db),
):
    """Return ecliptic longitudes of all transit planets for the given date.

    Used by the frontend to render transit planets on the natal wheel.
    chart_id is validated but positions are date-only (no chart dependency).
    """
    from datetime import date as date_type
    from backend.transit.engine import get_planet_positions_for_date

    chart = db.query(NatalChart).filter(NatalChart.id == chart_id).first()
    if not chart:
        raise HTTPException(status_code=404, detail=f"Chart not found: {chart_id}")

    try:
        query_date = date_type.fromisoformat(on_date)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid date format. Use YYYY-MM-DD.")

    planets = get_planet_positions_for_date(query_date)
    return {"date": on_date, "planets": planets}


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
    user: User | None = Depends(get_current_user_optional),
):
    """Stream an AI interpretation of all transits for a period.

    First calculates transits, then generates an overview interpretation
    via the AI fallback chain (GPT-4o → DeepSeek → templates).
    """
    tier_limiter.check_transit_access(user)
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
    user: User | None = Depends(get_current_user_optional),
):
    """Stream AI interpretation of a single transit event.

    Request body: transit event data (from /transits response).
    Used when user clicks on a specific event in the timeline.
    """
    tier_limiter.check_transit_access(user)
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


# ── Planner: monthly (no AI) ──────────────────────────────────────────────────
@app.get(
    "/api/v1/chart/{chart_id}/planner/monthly",
    tags=["planner"],
    summary="Monthly planner without AI — pure Python interpretation",
)
@limiter.limit(settings.rate_limit_anon)
async def get_monthly_planner(
    request: Request,
    chart_id: str,
    db: Session = Depends(get_db),
):
    import calendar as cal_mod
    from datetime import date as date_type
    from backend.transit.planner_engine import build_planner

    chart = db.query(NatalChart).filter(NatalChart.id == chart_id).first()
    if not chart:
        raise HTTPException(status_code=404, detail="Chart not found")

    if chart.time_unknown:
        return {"planner": {"error": "Время рождения неизвестно — планер недоступен."}}

    # today в timezone пользователя
    _tz = getattr(chart, "timezone", None)
    if _tz:
        try:
            import pytz as _pytz
            from datetime import datetime as _dt
            today = _dt.now(_pytz.timezone(_tz)).date()
        except Exception:
            today = date_type.today()
    else:
        today = date_type.today()

    month_start = today.replace(day=1)
    last_day = cal_mod.monthrange(today.year, today.month)[1]
    month_end = today.replace(day=last_day)

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



# ═══════════════════════════════════════════════════════════
# ASYNC TASK ENDPOINTS (Celery)
# ═══════════════════════════════════════════════════════════

@app.post(
    "/api/v1/chart/{chart_id}/transits/async",
    tags=["transits"],
    summary="Start async transit calculation (returns task_id)",
)
@limiter.limit(settings.rate_limit_anon)
async def start_transits_async(
    request: Request,
    chart_id: str,
    from_date: str,
    to_date: str,
    planet: str | None = None,
    max_orb: float | None = None,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    """Start heavy transit calculation as background Celery task.

    Returns task_id immediately. Poll GET /api/v1/tasks/{task_id}/status for result.
    Use instead of /transits when period > 3 months.
    """
    tier_limiter.check_transit_access(user)

    chart = db.query(NatalChart).filter(NatalChart.id == chart_id).first()
    if not chart:
        raise HTTPException(status_code=404, detail=f"Chart not found: {chart_id}")

    try:
        from_dt = __import__("datetime").date.fromisoformat(from_date)
        to_dt   = __import__("datetime").date.fromisoformat(to_date)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid date format. Use YYYY-MM-DD.")

    if to_dt <= from_dt:
        raise HTTPException(status_code=422, detail="to_date must be after from_date.")

    delta = (to_dt - from_dt).days
    if delta > 366:
        raise HTTPException(status_code=422, detail="Transit period cannot exceed 1 year.")

    from backend.tasks import task_calculate_transits
    task = task_calculate_transits.delay(
        chart_id=chart_id,
        from_date=from_date,
        to_date=to_date,
        planet_filter=planet,
        max_orb=max_orb,
    )

    return {"task_id": task.id, "status": "pending"}


@app.post(
    "/api/v1/chart/{chart_id}/pdf",
    tags=["chart"],
    summary="Start async PDF generation (returns task_id)",
)
@limiter.limit(settings.rate_limit_anon)
async def start_pdf_generation(
    request: Request,
    chart_id: str,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    """Start PDF report generation as background Celery task.

    Returns task_id immediately. Poll GET /api/v1/tasks/{task_id}/status for result.
    Result contains base64-encoded PDF.
    """
    chart = db.query(NatalChart).filter(NatalChart.id == chart_id).first()
    if not chart:
        raise HTTPException(status_code=404, detail=f"Chart not found: {chart_id}")

    from backend.tasks import task_generate_pdf
    task = task_generate_pdf.delay(chart_id=chart_id)

    return {"task_id": task.id, "status": "pending"}


@app.get(
    "/api/v1/tasks/{task_id}/status",
    tags=["tasks"],
    summary="Poll async task status and result",
)
async def get_task_status(task_id: str):
    """Poll the status of a background Celery task.

    Returns:
      - status: pending | started | success | failure
      - step: current step name (while running)
      - result: task result (when status=success)
      - error: error message (when status=failure)
    """
    from celery.result import AsyncResult
    from backend.celery_app import celery_app

    result = AsyncResult(task_id, app=celery_app)

    if result.state == "PENDING":
        return {"task_id": task_id, "status": "pending"}

    if result.state == "STARTED":
        meta = result.info or {}
        return {"task_id": task_id, "status": "started", "step": meta.get("step", "")}

    if result.state == "SUCCESS":
        return {"task_id": task_id, "status": "success", "result": result.result}

    if result.state == "FAILURE":
        return {"task_id": task_id, "status": "failure", "error": str(result.result)}

    return {"task_id": task_id, "status": result.state.lower()}


@app.get('/api/v1/debug/moon', tags=['debug'])
async def debug_moon():
    import swisseph as swe, os
    ephe_path = os.getenv('EPHE_PATH', 'data/ephe')
    swe.set_ephe_path(ephe_path)

    def _moon_angle(jd):
        sun, _ = swe.calc_ut(jd, swe.SUN, swe.FLG_SWIEPH)
        moon, _ = swe.calc_ut(jd, swe.MOON, swe.FLG_SWIEPH)
        return (moon[0] - sun[0]) % 360

    # Проверим значения угла вокруг 1 мая и 16 мая
    checks = []
    for label, y, mo, d, h in [
        ("30apr_17utc", 2026, 4, 30, 17.0),
        ("01may_00utc", 2026, 5, 1, 0.0),
        ("15may_20utc", 2026, 5, 15, 20.0),
        ("16may_06utc", 2026, 5, 16, 6.0),
        ("30may_08utc", 2026, 5, 30, 8.0),
        ("31may_08utc", 2026, 5, 31, 8.0),
    ]:
        jd = swe.julday(y, mo, d, h)
        angle = _moon_angle(jd)
        checks.append({"label": label, "angle": round(angle, 2)})

    return {"checks": checks}


# ═══════════════════════════════════════════════════════════
# GENERAL CALENDAR — бесплатный, без натальной карты
# ═══════════════════════════════════════════════════════════

@app.get(
    "/api/v1/calendar/monthly",
    tags=["calendar"],
    summary="General astro calendar for a month (free tier)",
)
@limiter.limit(settings.rate_limit_anon)
async def get_general_calendar(
    request: Request,
    month: str,           # формат: "2025-12"
):
    """Общий астро-календарь — новолуния, полнолуния, ингрессы, аспекты.
    Не требует натальной карты. Бесплатный уровень.
    Возвращает: список событий + AI-обзор месяца.
    """
    import httpx, os
    from backend.transit.forecast_prompt import build_general_calendar_prompt, parse_forecast_response

    try:
        year, mon = map(int, month.split("-"))
    except ValueError:
        raise HTTPException(status_code=422, detail="Формат: YYYY-MM (напр. 2025-12)")

    # 1. Вычислить события месяца
    key_events = get_monthly_calendar(year, mon)

    # 2. Сформировать обзор через AI
    month_names_ru = {
        1:"Январь",2:"Февраль",3:"Март",4:"Апрель",5:"Май",6:"Июнь",
        7:"Июль",8:"Август",9:"Сентябрь",10:"Октябрь",11:"Ноябрь",12:"Декабрь",
    }
    month_label = f"{month_names_ru[mon]} {year}"
    prompt = build_general_calendar_prompt(month_label=month_label, key_events=key_events)

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
            logger.warning(f"General calendar AI failed: {e}")

    overview = None
    if raw:
        try:
            overview = parse_forecast_response(raw)
        except Exception as e:
            logger.warning(f"Failed to parse calendar overview: {e}")

    return {
        "month": month,
        "events": key_events,
        "overview": overview,
    }


# ═══════════════════════════════════════════════════════════
# LUNAR CALENDAR
# ═══════════════════════════════════════════════════════════

@app.get(
    "/api/v1/calendar/lunar",
    tags=["calendar"],
    summary="Lunar calendar: moon phases + moon sign per day",
)
@limiter.limit(settings.rate_limit_anon)
async def get_lunar_calendar(
    request: Request,
    year: int = None,
    month: int = None,
):
    from datetime import date as date_type, datetime as dt_type
    from backend.calendar.lunar_engine import get_moon_phases, ZODIAC_SIGNS
    import swisseph as swe
    import calendar as cal_mod

    today = date_type.today()
    year  = year  or today.year
    month = month or today.month

    # Точный расчёт фаз через бисекцию
    def _moon_angle(jd):
        sun, _ = swe.calc_ut(jd, swe.SUN, swe.FLG_SWIEPH)
        moon, _ = swe.calc_ut(jd, swe.MOON, swe.FLG_SWIEPH)
        return (moon[0] - sun[0]) % 360

    jd_m0 = swe.julday(year, month, 1, 0)
    jd_m1 = swe.julday(year + 1, 1, 1, 0) if month == 12 else swe.julday(year, month + 1, 1, 0)
    phases = []
    for target, etype, emoji, label in [
        (0,   "new_moon",  "🌑", "Новолуние"),
        (180, "full_moon", "🌕", "Полнолуние"),
    ]:
        jd = jd_m0 - 32
        prev = None
        while jd < jd_m1 + 2:
            val = (_moon_angle(jd) - target) % 360
            if val > 180: val -= 360
            if prev is not None and prev * val < 0:
                lo, hi = jd - 1.0, jd
                val_lo = prev  # знак на левой границе
                for _ in range(60):
                    mid = (lo + hi) / 2
                    v = (_moon_angle(mid) - target) % 360
                    if v > 180: v -= 360
                    if val_lo * v > 0:
                        lo = mid
                        val_lo = v
                    else:
                        hi = mid
                exact = (lo + hi) / 2
                # Проверяем что нашли реальную фазу, а не разрыв функции
                real_angle = _moon_angle(exact)
                if abs((real_angle - target + 180) % 360 - 180) > 10:
                    prev = val
                    jd += 1.0
                    continue
                y2, mo2, d2, h2 = swe.revjul(exact)
                h2_gmt3 = h2 + 3
                d2_gmt3 = int(d2)
                mo2_gmt3 = int(mo2)
                y2_gmt3 = int(y2)
                if h2_gmt3 >= 24:
                    h2_gmt3 -= 24
                    d2_gmt3 += 1
                    import calendar as _cal
                    _, max_day = _cal.monthrange(y2_gmt3, mo2_gmt3)
                    if d2_gmt3 > max_day:
                        d2_gmt3 = 1
                        mo2_gmt3 += 1
                        if mo2_gmt3 > 12:
                            mo2_gmt3 = 1
                            y2_gmt3 += 1
                hh, mm = int(h2_gmt3), int((h2_gmt3 % 1) * 60)
                moon_lon, _ = swe.calc_ut(exact, swe.MOON, swe.FLG_SWIEPH)
                sign = ZODIAC_SIGNS[int(moon_lon[0] // 30) % 12]
                phases.append({
                    "date": f"{y2_gmt3:04d}-{mo2_gmt3:02d}-{d2_gmt3:02d}",
                    "time": f"{hh:02d}:{mm:02d} GMT+3",
                    "type": etype, "planet": "Moon",
                    "sign": sign, "emoji": emoji,
                    "description": f"{label} в {sign}",
                })
            prev = val
            jd += 1.0
        # Оставляем только фазы текущего месяца
    month_prefix = f"{year:04d}-{month:02d}-"
    phases = [p for p in phases if p["date"].startswith(month_prefix)]
    phases.sort(key=lambda x: x["date"])
  
    _, days_in_month = cal_mod.monthrange(year, month)
    daily_signs = []
    for day in range(1, days_in_month + 1):
        d = date_type(year, month, day)
        jd = swe.julday(d.year, d.month, d.day, 12.0)
        lon, _ = swe.calc_ut(jd, swe.MOON, swe.FLG_SWIEPH)
        sign = ZODIAC_SIGNS[int(lon[0] // 30) % 12]
        daily_signs.append({
            "date": d.isoformat(),
            "sign": sign,
            "longitude": round(lon[0], 2),
        })

    now = dt_type.utcnow()
    jd_now = swe.julday(now.year, now.month, now.day, now.hour + now.minute / 60)
    lon_now, _ = swe.calc_ut(jd_now, swe.MOON, swe.FLG_SWIEPH)
    current_sign   = ZODIAC_SIGNS[int(lon_now[0] // 30) % 12]
    current_degree = round(lon_now[0] % 30, 1)

    return {
        "year":  year,
        "month": month,
        "current_moon": {
            "sign":   current_sign,
            "degree": current_degree,
        },
        "phases":      phases,
        "daily_signs": daily_signs,
    }


# ── DEBUG: show house cusps ───────────────────────────────────────────────────
@app.get("/api/v1/chart/{chart_id}/debug/cusps", tags=["debug"])
async def get_chart_cusps(chart_id: str, db: Session = Depends(get_db)):
    chart = db.query(NatalChart).filter(NatalChart.id == chart_id).first()
    if not chart:
        raise HTTPException(status_code=404, detail="Chart not found")
    return {
        "timezone": getattr(chart, "timezone", None),
        "house_system": getattr(chart, "house_system", "unknown"),
        "houses": chart.houses,
    }
