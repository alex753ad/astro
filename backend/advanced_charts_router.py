"""Соляр, синастрия и релокация — расчёты и AI-интерпретации.

Доступ только администраторам (`users.is_admin`). Тариф здесь не проверяется,
но по-прежнему определяет модель AI и объём текста — через
`InterpretationRequest.tier`, как для натальной интерпретации.

Результаты не сохраняются в БД: карты соляра, партнёра и релокации считаются
на лету и возвращаются напрямую.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.admin.admin_router import require_admin
from backend.auth.dependencies import get_current_user_optional
from backend.database import get_db
from backend.ephemeris.calculator import calculate_full_chart
from backend.ephemeris.geo import GeocodingError, geocode_place, resolve_utc_datetime
from backend.ephemeris.solar_return import find_solar_return
from backend.ephemeris.synastry import calculate_synastry_aspects
from backend.models import NatalChart, User
from backend.schemas import (
    AspectData,
    HouseData,
    NatalChartResponse,
    PlanetPosition,
    PointData,
)

logger = logging.getLogger("astro.advanced")

router = APIRouter(prefix="/api/v1/chart", tags=["advanced"])

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


# ═══════════════════════════════════════════════════════════
# СХЕМЫ
# ═══════════════════════════════════════════════════════════

class SolarReturnRequest(BaseModel):
    year: int = Field(..., ge=1900, le=2100)
    location: Optional[str] = Field(None, max_length=255)


class PartnerData(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    birth_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    birth_time: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    birth_place: str = Field(..., min_length=2, max_length=255)
    house_system: str = Field("placidus", pattern=r"^(placidus|koch|whole_sign|equal)$")


class SynastryRequest(BaseModel):
    chart_id: str
    partner: PartnerData


class RelocationRequest(BaseModel):
    location: str = Field(..., min_length=2, max_length=255)


class SolarReturnResponse(NatalChartResponse):
    solar_return_datetime: str


class RelocationResponse(NatalChartResponse):
    relocated_location: str


class SynastryResponse(BaseModel):
    chart1: NatalChartResponse
    chart2: NatalChartResponse
    cross_aspects: list[AspectData]


# ═══════════════════════════════════════════════════════════
# ОБЩИЕ ХЕЛПЕРЫ
# ═══════════════════════════════════════════════════════════

def _load_chart(chart_id: str, user: User, request: Request, db: Session) -> NatalChart:
    """Карта по id с проверкой доступа.

    Импорт отложенный: backend.main подключает этот роутер, поэтому импорт на
    уровне модуля дал бы цикл.
    """
    from backend.main import chart_token, resolve_chart_access

    return resolve_chart_access(chart_id, user, chart_token(request), db)


def _require_admin_user(user: User | None) -> User:
    """Админ-гейт для SSE-эндпоинтов, где аутентификация идёт через тикет.

    Тикет выдаётся любому пользователю (он общий для всех SSE в приложении,
    включая натальную интерпретацию), поэтому роль проверяется здесь.
    """
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Требуется авторизация.")
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin access required")
    return user


def _chart_to_response(chart_data, aspects, time_unknown: bool, **extra) -> dict:
    """Сборка полей NatalChartResponse из результата calculate_full_chart()."""
    return {
        "planets": [
            PlanetPosition(
                name=p.name,
                longitude=p.longitude,
                sign=p.sign,
                degree_in_sign=p.degree_in_sign,
                house=p.house if not time_unknown else None,
                retrograde=p.retrograde,
            )
            for p in chart_data.planets
        ],
        "houses": [
            HouseData(number=h.number, sign=h.sign, degree=h.degree)
            for h in chart_data.houses
        ],
        "aspects": [
            AspectData(
                planet1=a.planet1,
                planet2=a.planet2,
                aspect_type=a.aspect_type,
                angle=a.angle,
                orb=a.orb,
                applying=a.applying,
                importance=getattr(a, "importance", "low"),
            )
            for a in aspects
        ],
        "ascendant": PointData(
            sign=chart_data.ascendant.sign,
            degree=chart_data.ascendant.degree,
            longitude=chart_data.ascendant.longitude,
        ) if chart_data.ascendant else None,
        "midheaven": PointData(
            sign=chart_data.midheaven.sign,
            degree=chart_data.midheaven.degree,
            longitude=chart_data.midheaven.longitude,
        ) if chart_data.midheaven else None,
        "time_unknown": time_unknown,
        **extra,
    }


def _natal_profile(chart: NatalChart) -> dict:
    """Профиль сохранённой карты для промпта."""
    return {
        "planets": chart.planets,
        "houses": chart.houses,
        "aspects": chart.aspects,
        "ascendant": chart.ascendant,
        "midheaven": chart.midheaven,
        "time_unknown": chart.time_unknown,
    }


def _profile_from_payload(payload: dict) -> dict:
    """Профиль рассчитанной на лету карты для промпта."""
    return {
        "planets": [p.model_dump() for p in payload["planets"]],
        "houses": [h.model_dump() for h in payload["houses"]],
        "aspects": [a.model_dump() for a in payload["aspects"]],
        "ascendant": payload["ascendant"].model_dump() if payload["ascendant"] else None,
        "midheaven": payload["midheaven"].model_dump() if payload["midheaven"] else None,
        "time_unknown": payload["time_unknown"],
    }


async def _resolve_location(location: str | None, chart: NatalChart) -> tuple[float, float, str, str]:
    """(lat, lon, timezone, display_name) — из локации или из натальной карты."""
    if not location:
        return chart.latitude, chart.longitude, chart.timezone, chart.birth_place
    try:
        geo = await geocode_place(location)
    except GeocodingError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    return geo.latitude, geo.longitude, geo.timezone, geo.display_name


def _stream_interpretation(prompt: str, profile: dict, context: str, tier: str, fallback: str):
    """SSE-генератор поверх каскада движков.

    Повторяет схему стриминга транзитов: движки по очереди, шаблон — на случай,
    если ни один не ответил.
    """
    from backend.interpretation.base import InterpretationRequest
    from backend.interpretation.router import get_router

    ai_router = get_router()

    async def event_stream():
        try:
            interp_request = InterpretationRequest(
                natal_profile=profile,
                context=context,
                tier=tier,
                custom_prompt=prompt,
            )

            for engine in ai_router._engines:
                if engine.name == "template":
                    continue
                if not ai_router._check_budget(engine.name):
                    continue
                try:
                    streamed = False
                    async for chunk in engine.stream(interp_request):
                        yield f"data: {json.dumps({'text': chunk}, ensure_ascii=False)}\n\n"
                        streamed = True
                    if streamed:
                        yield "data: [DONE]\n\n"
                        return
                except Exception as exc:  # noqa: BLE001
                    logger.error("%s stream from %s failed: %s", context, engine.name, exc)
                    continue

            yield f"data: {json.dumps({'text': fallback}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

        except Exception as exc:  # noqa: BLE001
            logger.exception("%s interpretation stream failed", context)
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream", headers=SSE_HEADERS)


# ═══════════════════════════════════════════════════════════
# СОЛЯР
# ═══════════════════════════════════════════════════════════

async def _build_solar_return(chart: NatalChart, year: int, location: str | None) -> dict:
    natal_sun = next(
        (p for p in (chart.planets or []) if p.get("name") == "Sun"), None
    )
    if natal_sun is None or chart.utc_datetime is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "В карте нет данных о Солнце или времени рождения — соляр не рассчитать.",
        )

    exact_dt = find_solar_return(
        natal_sun_longitude=float(natal_sun["longitude"]),
        natal_dt=chart.utc_datetime,
        year=year,
    )

    lat, lon, _tz, display_name = await _resolve_location(location, chart)

    chart_data, aspects = calculate_full_chart(
        utc_dt=exact_dt,
        latitude=lat,
        longitude=lon,
        house_system=chart.house_system or "placidus",
        time_unknown=False,  # момент соляра известен с точностью до секунд
    )

    payload = _chart_to_response(chart_data, aspects, time_unknown=False)
    payload.update({
        "birth_date": exact_dt.strftime("%Y-%m-%d"),
        "birth_time": exact_dt.strftime("%H:%M"),
        "birth_place": display_name,
        "latitude": lat,
        "longitude": lon,
        "timezone": _tz,
        "house_system": chart.house_system or "placidus",
        "solar_return_datetime": exact_dt.isoformat(),
    })
    return payload


@router.post(
    "/{chart_id}/solar-return",
    response_model=SolarReturnResponse,
    summary="Карта солнечного возвращения (соляр)",
)
async def calculate_solar_return(
    request: Request,
    chart_id: str,
    data: SolarReturnRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    chart = _load_chart(chart_id, admin, request, db)
    return SolarReturnResponse(**await _build_solar_return(chart, data.year, data.location))


@router.get(
    "/{chart_id}/solar-return/{year}/interpret",
    summary="Интерпретация соляра (SSE)",
)
async def interpret_solar_return(
    request: Request,
    chart_id: str,
    year: int,
    location: str | None = None,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    admin = _require_admin_user(user)
    chart = _load_chart(chart_id, admin, request, db)

    payload = await _build_solar_return(chart, year, location)

    from backend.interpretation.advanced_prompts import build_solar_return_prompt

    prompt = build_solar_return_prompt(
        solar_profile=_profile_from_payload(payload),
        natal_profile=_natal_profile(chart),
        year=year,
        exact_moment=payload["solar_return_datetime"],
        location=location,
    )
    return _stream_interpretation(
        prompt=prompt,
        profile=_profile_from_payload(payload),
        context="solar_return",
        tier=admin.tier or "free",
        fallback=(
            f"Соляр на {year} год рассчитан на момент "
            f"{payload['solar_return_datetime']}. AI-разбор сейчас недоступен — "
            "попробуйте позже."
        ),
    )


# ═══════════════════════════════════════════════════════════
# СИНАСТРИЯ
# ═══════════════════════════════════════════════════════════

async def _build_synastry(chart: NatalChart, partner: PartnerData) -> dict:
    try:
        geo = await geocode_place(partner.birth_place)
    except GeocodingError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))

    utc_dt, time_unknown, _warnings = resolve_utc_datetime(
        birth_date=partner.birth_date,
        birth_time=partner.birth_time,
        timezone=geo.timezone,
    )

    partner_data, partner_aspects = calculate_full_chart(
        utc_dt=utc_dt,
        latitude=geo.latitude,
        longitude=geo.longitude,
        house_system=partner.house_system,
        time_unknown=time_unknown,
    )

    chart2 = _chart_to_response(partner_data, partner_aspects, time_unknown)
    chart2.update({
        "name": partner.name,
        "birth_date": partner.birth_date,
        "birth_time": partner.birth_time,
        "birth_place": geo.display_name,
        "latitude": geo.latitude,
        "longitude": geo.longitude,
        "timezone": geo.timezone,
        "house_system": partner.house_system,
    })

    chart1 = {
        "id": chart.id,
        "name": chart.name,
        "birth_date": chart.birth_date,
        "birth_time": chart.birth_time,
        "birth_place": chart.birth_place,
        "latitude": chart.latitude,
        "longitude": chart.longitude,
        "timezone": chart.timezone,
        "time_unknown": bool(chart.time_unknown),
        "house_system": chart.house_system or "placidus",
        "planets": [PlanetPosition(**p) for p in chart.planets],
        "houses": [HouseData(**h) for h in chart.houses],
        "aspects": [AspectData(**a) for a in chart.aspects],
        "ascendant": PointData(**chart.ascendant) if chart.ascendant else None,
        "midheaven": PointData(**chart.midheaven) if chart.midheaven else None,
    }

    # Планеты сохранённой карты лежат в БД словарями — приводим к тому же виду,
    # что и у рассчитанной, чтобы сравнивать их одной функцией.
    from backend.ephemeris.calculator import PlanetResult

    planets1 = [
        PlanetResult(
            name=p["name"], longitude=p["longitude"], latitude=0.0, distance=1.0,
            speed=0.0, sign=p.get("sign", ""), degree_in_sign=p.get("degree_in_sign", 0.0),
            retrograde=p.get("retrograde", False),
        )
        for p in chart.planets
    ]

    cross = calculate_synastry_aspects(planets1, partner_data.planets)
    cross_aspects = [
        AspectData(
            planet1=a.planet1, planet2=a.planet2, aspect_type=a.aspect_type,
            angle=a.angle, orb=a.orb, applying=a.applying, importance=a.importance,
        )
        for a in cross
    ]

    return {"chart1": chart1, "chart2": chart2, "cross_aspects": cross_aspects}


@router.post("/synastry", response_model=SynastryResponse, summary="Синастрия двух карт")
async def calculate_synastry(
    request: Request,
    data: SynastryRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    chart = _load_chart(data.chart_id, admin, request, db)
    result = await _build_synastry(chart, data.partner)
    return SynastryResponse(
        chart1=NatalChartResponse(**result["chart1"]),
        chart2=NatalChartResponse(**result["chart2"]),
        cross_aspects=result["cross_aspects"],
    )


@router.post("/synastry/interpret", summary="Интерпретация синастрии (SSE)")
async def interpret_synastry(
    request: Request,
    data: SynastryRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    chart = _load_chart(data.chart_id, admin, request, db)
    result = await _build_synastry(chart, data.partner)

    from backend.interpretation.advanced_prompts import build_synastry_prompt

    profile1 = _natal_profile(chart)
    profile2 = _profile_from_payload(result["chart2"])

    prompt = build_synastry_prompt(
        chart1_profile=profile1,
        chart2_profile=profile2,
        cross_aspects=[a.model_dump() for a in result["cross_aspects"]],
        name1=chart.name or "Первый партнёр",
        name2=data.partner.name or "Второй партнёр",
    )
    return _stream_interpretation(
        prompt=prompt,
        profile=profile1,
        context="synastry",
        tier=admin.tier or "free",
        fallback=(
            f"Найдено {len(result['cross_aspects'])} межкарточных аспектов. "
            "AI-разбор совместимости сейчас недоступен — попробуйте позже."
        ),
    )


# ═══════════════════════════════════════════════════════════
# РЕЛОКАЦИЯ
# ═══════════════════════════════════════════════════════════

async def _build_relocation(chart: NatalChart, location: str) -> dict:
    if chart.utc_datetime is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "В карте нет момента рождения в UTC — релокацию не рассчитать.",
        )

    try:
        geo = await geocode_place(location)
    except GeocodingError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))

    time_unknown = bool(chart.time_unknown)

    # Момент рождения тот же — меняются только координаты.
    chart_data, aspects = calculate_full_chart(
        utc_dt=chart.utc_datetime,
        latitude=geo.latitude,
        longitude=geo.longitude,
        house_system=chart.house_system or "placidus",
        time_unknown=time_unknown,
    )

    payload = _chart_to_response(chart_data, aspects, time_unknown)
    payload.update({
        "name": chart.name,
        "birth_date": chart.birth_date,
        "birth_time": chart.birth_time,
        "birth_place": geo.display_name,
        "latitude": geo.latitude,
        "longitude": geo.longitude,
        "timezone": geo.timezone,
        "house_system": chart.house_system or "placidus",
        "relocated_location": geo.display_name,
    })
    return payload


@router.post(
    "/{chart_id}/relocation",
    response_model=RelocationResponse,
    summary="Релокационная карта",
)
async def calculate_relocation(
    request: Request,
    chart_id: str,
    data: RelocationRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    chart = _load_chart(chart_id, admin, request, db)
    return RelocationResponse(**await _build_relocation(chart, data.location))


@router.get("/{chart_id}/relocation/interpret", summary="Интерпретация релокации (SSE)")
async def interpret_relocation(
    request: Request,
    chart_id: str,
    location: str,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    admin = _require_admin_user(user)
    chart = _load_chart(chart_id, admin, request, db)

    payload = await _build_relocation(chart, location)

    from backend.interpretation.advanced_prompts import build_relocation_prompt

    prompt = build_relocation_prompt(
        relocated_profile=_profile_from_payload(payload),
        natal_profile=_natal_profile(chart),
        location=payload["relocated_location"],
    )
    return _stream_interpretation(
        prompt=prompt,
        profile=_profile_from_payload(payload),
        context="relocation",
        tier=admin.tier or "free",
        fallback=(
            f"Релокационная карта для «{payload['relocated_location']}» рассчитана. "
            "AI-разбор сейчас недоступен — попробуйте позже."
        ),
    )
