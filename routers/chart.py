"""Chart router — natal chart calculation and AI interpretation."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.database import get_db
from backend.schemas import (
    BirthDataInput,
    NatalChartResponse,
    PlanetPosition,
    HouseData,
    AspectData,
    PointData,
    ErrorResponse,
)
from backend.models import NatalChart, User
from backend.ephemeris.calculator import calculate_full_chart
from backend.ephemeris.geo import (
    geocode_place,
    resolve_utc_datetime,
    validate_coordinates,
    GeocodingError,
    AmbiguousTimeError,
)
from backend.auth.dependencies import get_current_user_optional
from backend.auth.rate_limits import tier_limiter
from backend.limiter import limiter

logger = logging.getLogger("astro")
settings = get_settings()

router = APIRouter(prefix="/api/v1/chart", tags=["chart"])


@router.post(
    "/calculate",
    response_model=NatalChartResponse,
    responses={422: {"model": ErrorResponse}, 400: {"model": ErrorResponse}},
    summary="Calculate natal chart",
)
@limiter.limit(settings.rate_limit_anon)
async def calculate_chart(
    request: Request,
    data: BirthDataInput,
    db: Session = Depends(get_db),
):
    warnings: list[str] = []

    try:
        geo = await geocode_place(data.birth_place)
    except GeocodingError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        coord_warnings = validate_coordinates(geo.latitude, geo.longitude)
        warnings.extend(coord_warnings)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

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
            detail={"message": str(e), "options": e.options, "type": "ambiguous_time"},
        )

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
    houses_resp = [HouseData(number=h.number, sign=h.sign, degree=h.degree) for h in chart_data.houses]
    aspects_resp = [
        AspectData(
            planet1=a.planet1, planet2=a.planet2,
            aspect_type=a.aspect_type, angle=a.angle, orb=a.orb, applying=a.applying,
        )
        for a in aspects
    ]
    asc_resp = PointData(sign=chart_data.ascendant.sign, degree=chart_data.ascendant.degree, longitude=chart_data.ascendant.longitude) if chart_data.ascendant else None
    mc_resp  = PointData(sign=chart_data.midheaven.sign, degree=chart_data.midheaven.degree, longitude=chart_data.midheaven.longitude) if chart_data.midheaven else None

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


@router.get(
    "/{chart_id}",
    response_model=NatalChartResponse,
    responses={404: {"model": ErrorResponse}},
    summary="Get saved chart",
)
@limiter.limit(settings.rate_limit_anon)
async def get_chart(request: Request, chart_id: str, db: Session = Depends(get_db)):
    chart = db.query(NatalChart).filter(NatalChart.id == chart_id).first()
    if not chart:
        raise HTTPException(status_code=404, detail=f"Chart not found: {chart_id}")

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
        planets=[PlanetPosition(**p) for p in chart.planets],
        houses=[HouseData(**h) for h in chart.houses],
        aspects=[AspectData(**a) for a in chart.aspects],
        ascendant=PointData(**chart.ascendant) if chart.ascendant else None,
        midheaven=PointData(**chart.midheaven) if chart.midheaven else None,
    )


@router.get("/{chart_id}/interpret", tags=["interpretation"], summary="Stream AI interpretation (SSE)")
@limiter.limit(settings.rate_limit_anon)
async def interpret_chart(
    request: Request,
    chart_id: str,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    tier_limiter.check_interpretation_limit(user)
    from backend.interpretation.base import InterpretationRequest
    from backend.interpretation.router import get_router

    chart = db.query(NatalChart).filter(NatalChart.id == chart_id).first()
    if not chart:
        raise HTTPException(status_code=404, detail=f"Chart not found: {chart_id}")

    profile = {
        "planets": chart.planets, "houses": chart.houses, "aspects": chart.aspects,
        "ascendant": chart.ascendant, "midheaven": chart.midheaven, "time_unknown": chart.time_unknown,
    }
    interp_request = InterpretationRequest(natal_profile=profile)
    ai_router = get_router()

    full_text = []

    async def event_stream():
        try:
            async for chunk in ai_router.stream(interp_request):
                full_text.append(chunk)
                yield f"data: {json.dumps({'text': chunk}, ensure_ascii=False)}\n\n"
            # Save to DB after streaming completes (own session — original may be closed)
            content = "".join(full_text)
            if content:
                try:
                    from backend.models import Interpretation
                    from backend.database import SessionLocal
                    from backend.cache import make_profile_hash
                    save_db = SessionLocal()
                    try:
                        profile_hash = make_profile_hash(profile)
                        existing = save_db.query(Interpretation).filter(
                            Interpretation.chart_id == chart_id,
                        ).first()
                        if not existing:
                            save_db.add(Interpretation(
                                chart_id=chart_id,
                                profile_hash=profile_hash,
                                engine="stream",
                                content=content,
                            ))
                            save_db.commit()
                            logger.info("Saved interpretation to DB for chart %s, len=%d", chart_id, len(content))
                    finally:
                        save_db.close()
                except Exception as save_exc:
                    logger.exception("Failed to save interpretation to DB: %s", save_exc)
            yield "data: [DONE]\n\n"
        except Exception as e:
            logger.exception("Streaming interpretation failed")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.post("/{chart_id}/interpret", tags=["interpretation"], summary="Generate full interpretation (non-streaming)")
@limiter.limit(settings.rate_limit_anon)
async def interpret_chart_full(
    request: Request,
    chart_id: str,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    tier_limiter.check_interpretation_limit(user)
    from backend.interpretation.base import InterpretationRequest
    from backend.interpretation.router import get_router

    chart = db.query(NatalChart).filter(NatalChart.id == chart_id).first()
    if not chart:
        raise HTTPException(status_code=404, detail=f"Chart not found: {chart_id}")

    profile = {
        "planets": chart.planets, "houses": chart.houses, "aspects": chart.aspects,
        "ascendant": chart.ascendant, "midheaven": chart.midheaven, "time_unknown": chart.time_unknown,
    }
    interp_request = InterpretationRequest(natal_profile=profile)
    ai_router = get_router()
    result = await ai_router.generate(interp_request)

    # Save to DB
    if result.content:
        try:
            from backend.models import Interpretation
            from backend.cache import make_profile_hash
            profile_hash = make_profile_hash(profile)
            existing = db.query(Interpretation).filter(
                Interpretation.chart_id == chart_id,
            ).first()
            if not existing:
                db.add(Interpretation(
                    chart_id=chart_id,
                    profile_hash=profile_hash,
                    engine=result.engine or "api",
                    content=result.content,
                    sections=result.sections,
                ))
                db.commit()
                logger.info("Saved interpretation to DB for chart %s, len=%d", chart_id, len(result.content))
        except Exception as save_exc:
            logger.exception("Failed to save interpretation to DB: %s", save_exc)

    return {"chart_id": chart_id, "content": result.content, "sections": result.sections, "engine": result.engine, "cached": result.cached}


@router.get("/{chart_id}/debug/cusps", tags=["debug"])
async def get_chart_cusps(chart_id: str, db: Session = Depends(get_db)):
    chart = db.query(NatalChart).filter(NatalChart.id == chart_id).first()
    if not chart:
        raise HTTPException(status_code=404, detail="Chart not found")
    return {
        "timezone": getattr(chart, "timezone", None),
        "house_system": getattr(chart, "house_system", "unknown"),
        "houses": chart.houses,
    }
