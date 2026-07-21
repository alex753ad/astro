"""CRM router for astrologers (Premium only).

Endpoints:
  POST   /api/v1/clients              — create client
  GET    /api/v1/clients              — list clients (search ?q=)
  GET    /api/v1/clients/{id}         — client card
  PATCH  /api/v1/clients/{id}         — update notes
  DELETE /api/v1/clients/{id}         — delete client
  GET    /api/v1/clients/{id}/chart   — calculate/get client chart
  GET    /api/v1/clients/{id}/transits — client transits for period
  POST   /api/v1/clients/{id}/report  — generate PDF (Celery task)
"""

from __future__ import annotations

import json
import hashlib
import logging
import secrets
import os
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import AstrologerProfile, ClientPortalAccess, ClientProfile, Consultation, NatalChart, User
from backend.auth.dependencies import get_current_user, require_tier

logger = logging.getLogger("astro.crm")

router = APIRouter(prefix="/api/v1/clients", tags=["crm"])

_premium = Depends(require_tier("premium"))
from backend.crm.access import crm_read, crm_write
_read = Depends(crm_read)     # GET — витрина (экс-пилот read-only)
_write = Depends(crm_write)   # мутации — только активный premium


# ── Schemas ──

class ClientCreate(BaseModel):
    name: str
    birth_date: date
    birth_time: Optional[str] = None
    birth_place: str
    notes: Optional[str] = None
    email: Optional[str] = None
    status: Optional[str] = None
    source: Optional[str] = None
    tags: Optional[list[str]] = None
    natal_chart_id: Optional[str] = None


class ClientPatch(BaseModel):
    notes: Optional[str] = None
    name: Optional[str] = None
    email: Optional[str] = None
    status: Optional[str] = None
    source: Optional[str] = None
    tags: Optional[list[str]] = None
    natal_chart_id: Optional[str] = None


class ClientOut(BaseModel):
    id: int
    name: str
    birth_date: date
    birth_time: Optional[str] = None
    birth_place: str
    notes: Optional[str] = None
    email: Optional[str] = None
    status: Optional[str] = None
    source: Optional[str] = None
    tags: Optional[list[str]] = None
    natal_chart_id: Optional[str] = None

    model_config = {"from_attributes": True}

    @field_validator("birth_time", mode="before")
    @classmethod
    def coerce_time(cls, v):
        import datetime
        if isinstance(v, datetime.time):
            return v.strftime("%H:%M")
        return v


class ConsultationCreate(BaseModel):
    date: Optional[datetime] = None
    topic: Optional[str] = None
    notes: Optional[str] = None
    assignment: Optional[str] = None
    next_date: Optional[datetime] = None
    price: Optional[int] = None
    status: str = "done"
    question_moment: Optional[datetime] = None
    question_place: Optional[str] = None


class ConsultationPatch(BaseModel):
    date: Optional[datetime] = None
    topic: Optional[str] = None
    notes: Optional[str] = None
    assignment: Optional[str] = None
    next_date: Optional[datetime] = None
    price: Optional[int] = None
    status: Optional[str] = None


class ConsultationOut(BaseModel):
    id: int
    client_id: int
    date: datetime
    topic: Optional[str] = None
    notes: Optional[str] = None
    assignment: Optional[str] = None
    next_date: Optional[datetime] = None
    price: Optional[int] = None
    status: str
    question_moment: Optional[datetime] = None
    question_place: Optional[str] = None
    horary_chart_id: Optional[str] = None

    model_config = {"from_attributes": True}


# ── Helpers ──

def _get_astrologer(user: User, db: Session) -> AstrologerProfile:
    profile = db.query(AstrologerProfile).filter(AstrologerProfile.user_id == user.id).first()
    if not profile:
        profile = AstrologerProfile(user_id=user.id, display_name=user.name or user.email)
        db.add(profile)
        db.commit()
        db.refresh(profile)
    return profile


def _get_client_or_404(client_id: int, astrologer: AstrologerProfile, db: Session) -> ClientProfile:
    client = db.query(ClientProfile).filter(
        ClientProfile.id == client_id,
        ClientProfile.astrologer_id == astrologer.id,
    ).first()
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    return client


def _get_consultation_or_404(consultation_id: int, client: ClientProfile, db: Session) -> Consultation:
    consultation = db.query(Consultation).filter(
        Consultation.id == consultation_id,
        Consultation.client_id == client.id,
    ).first()
    if not consultation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Consultation not found")
    return consultation


# ── Endpoints ──

async def _geocode_and_build_chart(db: Session, *, user_id: str, date_str: str, time_str, place: str) -> NatalChart:
    """Геокодит место + считает карту через движок + сохраняет NatalChart. Возвращает строку карты.
    Используется и для клиента, и для хорар-карты (026/027)."""
    from backend.ephemeris.geo import geocode_place, resolve_utc_datetime
    from backend.ephemeris.calculator import calculate_full_chart

    geo = await geocode_place(place)
    utc_dt, time_unknown, _ = resolve_utc_datetime(
        birth_date=date_str, birth_time=time_str, timezone=geo.timezone,
    )
    (chart_data, aspects) = calculate_full_chart(
        utc_dt=utc_dt, latitude=geo.latitude, longitude=geo.longitude,
        house_system="placidus", time_unknown=time_unknown,
    )
    chart = NatalChart(
        user_id=user_id,
        birth_date=date_str,
        birth_time=time_str,
        birth_place=geo.display_name,
        latitude=geo.latitude,
        longitude=geo.longitude,
        timezone=geo.timezone,
        utc_datetime=utc_dt,
        time_unknown=time_unknown,
        house_system="placidus",
        planets=[{
            "name": p.name, "longitude": p.longitude, "sign": p.sign,
            "degree_in_sign": p.degree_in_sign,
            "house": p.house if not time_unknown else None,
            "retrograde": p.retrograde,
        } for p in chart_data.planets],
        houses=[{"number": h.number, "sign": h.sign, "degree": h.degree} for h in chart_data.houses],
        aspects=[{
            "planet1": a.planet1, "planet2": a.planet2, "aspect_type": a.aspect_type,
            "angle": a.angle, "orb": a.orb, "applying": a.applying,
            "importance": getattr(a, "importance", "low"),
        } for a in aspects],
        ascendant={"sign": chart_data.ascendant.sign, "degree": chart_data.ascendant.degree, "longitude": chart_data.ascendant.longitude} if chart_data.ascendant else None,
        midheaven={"sign": chart_data.midheaven.sign, "degree": chart_data.midheaven.degree, "longitude": chart_data.midheaven.longitude} if chart_data.midheaven else None,
    )
    db.add(chart)
    db.commit()
    db.refresh(chart)
    return chart


@router.post("", response_model=ClientOut, status_code=status.HTTP_201_CREATED)
async def create_client(
    payload: ClientCreate,
    user: User = _write,
    db: Session = Depends(get_db),
):
    astrologer = _get_astrologer(user, db)
    client = ClientProfile(
        astrologer_id=astrologer.id,
        name=payload.name,
        birth_date=payload.birth_date,
        birth_time=payload.birth_time,
        birth_place=payload.birth_place,
        notes=payload.notes,
        email=payload.email,
        status=payload.status or "lead",
        source=payload.source,
        tags=payload.tags,
    )
    db.add(client)
    db.commit()
    db.refresh(client)

    # Если карта уже есть — просто привязываем, не пересчитываем
    if payload.natal_chart_id is not None:
        chart = db.query(NatalChart).filter(
            NatalChart.id == payload.natal_chart_id,
            NatalChart.user_id == user.id,
        ).first()
        if chart:
            client.natal_chart_id = payload.natal_chart_id
            db.commit()
            db.refresh(client)
        return client

    # Автоматически считаем натальную карту
    try:
        chart = await _geocode_and_build_chart(
            db, user_id=user.id,
            date_str=str(payload.birth_date), time_str=payload.birth_time,
            place=payload.birth_place,
        )
        client.natal_chart_id = chart.id
        db.commit()
        db.refresh(client)
    except Exception as e:
        logger.warning("Auto chart calculation failed for client %s: %s", client.id, e)

    return client


@router.get("", response_model=list[ClientOut])
async def list_clients(
    q: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    user: User = _read,
    db: Session = Depends(get_db),
):
    astrologer = _get_astrologer(user, db)
    query = db.query(ClientProfile).filter(ClientProfile.astrologer_id == astrologer.id)
    if q:
        query = query.filter(ClientProfile.name.ilike(f"%{q}%"))
    if status_filter:
        query = query.filter(ClientProfile.status == status_filter)
    return query.order_by(ClientProfile.created_at.desc()).all()


@router.get("/analytics")
async def get_analytics(
    user: User = _read,
    db: Session = Depends(get_db),
):
    """Агрегированная статистика по базе клиентов астролога."""
    from collections import Counter, defaultdict
    from datetime import datetime, timezone

    astrologer = _get_astrologer(user, db)

    rows = (
        db.query(ClientProfile, NatalChart)
        .outerjoin(NatalChart, ClientProfile.natal_chart_id == NatalChart.id)
        .filter(ClientProfile.astrologer_id == astrologer.id)
        .all()
    )

    all_clients   = [c for c, _ in rows]
    total_clients = len(all_clients)

    # Добавлено в этом месяце
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    added_this_month = sum(
        1 for c in all_clients
        if c.created_at and c.created_at.replace(tzinfo=timezone.utc) >= month_start
    )

    # Топ знаков Солнца
    sun_signs = []
    for _, chart in rows:
        if not chart:
            continue
        sun = next((p for p in (chart.planets or []) if p.get("name") == "Sun"), None)
        if sun and sun.get("sign"):
            sun_signs.append(sun["sign"])
    top_sun_signs = [{"sign": s, "count": c} for s, c in Counter(sun_signs).most_common(5)]

    # Топ городов
    cities = [c.birth_place.split(",")[0].strip() for c in all_clients if c.birth_place]
    top_cities = [{"city": ci, "count": cnt} for ci, cnt in Counter(cities).most_common(5)]

    # Рост базы: последние 6 месяцев
    monthly: dict[str, int] = defaultdict(int)
    for c in all_clients:
        if c.created_at:
            monthly[c.created_at.strftime("%Y-%m")] += 1
    clients_by_month = []
    for i in range(5, -1, -1):
        mo = now.month - i
        yr = now.year
        while mo < 1:
            mo += 12; yr -= 1
        key = f"{yr:04d}-{mo:02d}"
        clients_by_month.append({"month": key, "count": monthly.get(key, 0)})

    # PDF-отчёты — через calendar_export_logs пока нет таблицы reports
    reports_generated = 0
    try:
        from backend.models import CalendarExportLog
        reports_generated = (
            db.query(CalendarExportLog)
            .filter(CalendarExportLog.user_id == user.id, CalendarExportLog.status == "success")
            .count()
        )
    except Exception:
        pass

    return {
        "total_clients":       total_clients,
        "added_this_month":    added_this_month,
        "reports_generated":   reports_generated,
        "bookings_this_month": 0,  # TODO: таблица bookings не реализована
        "top_sun_signs":       top_sun_signs,
        "top_cities":          top_cities,
        "clients_by_month":    clients_by_month,
    }


@router.get("/dashboard-widgets")
async def get_dashboard_widgets(
    user: User = _read,
    db: Session = Depends(get_db),
):
    """Данные для нижней панели дашборда: ближайшая запись, ретроградные
    планеты (тренды месяца) и статус Premium. Один read-only запрос."""
    from datetime import timezone
    from backend.models import Subscription
    from backend.transit.engine import get_planet_positions_for_date

    astrologer = _get_astrologer(user, db)
    now = datetime.now(timezone.utc)

    # 1) Ближайшая запланированная консультация среди всех клиентов астролога
    row = (
        db.query(Consultation, ClientProfile.name)
        .join(ClientProfile, Consultation.client_id == ClientProfile.id)
        .filter(
            ClientProfile.astrologer_id == astrologer.id,
            Consultation.status == "planned",
            Consultation.date >= now.replace(tzinfo=None),
        )
        .order_by(Consultation.date.asc())
        .first()
    )
    next_appointment = None
    if row:
        cons, client_name = row
        next_appointment = {"client_name": client_name, "date": cons.date.isoformat()}

    # 2) Текущие ретроградные планеты (тренды месяца)
    retrogrades = [
        p["name"] for p in get_planet_positions_for_date(now.date())
        if p.get("retrograde")
    ]

    # 3) Premium: тир и дней до конца оплаченного периода
    days_left = None
    sub = (
        db.query(Subscription)
        .filter(Subscription.user_id == user.id, Subscription.status == "active")
        .order_by(Subscription.current_period_end.desc().nullslast())
        .first()
    )
    if sub and sub.current_period_end:
        delta = sub.current_period_end - now.replace(tzinfo=None)
        days_left = max(0, delta.days)

    return {
        "next_appointment": next_appointment,
        "retrogrades": retrogrades,
        "premium": {"tier": user.tier, "days_left": days_left},
    }


@router.get("/search", response_model=list[ClientOut])
async def search_clients(
    sun_sign:       Optional[str] = Query(None),
    moon_sign:      Optional[str] = Query(None),
    asc_sign:       Optional[str] = Query(None),
    planet:         Optional[str] = Query(None),
    house:          Optional[int] = Query(None, ge=1, le=12),
    user: User = _read,
    db: Session = Depends(get_db),
):
    """Поиск клиентов по астрологическим параметрам.
    Планеты и дома хранятся в natal_charts.planets как JSON —
    фильтруем на Python-уровне (< 500 клиентов у астролога).
    """
    astrologer = _get_astrologer(user, db)

    # Загружаем клиентов с натальными картами одним запросом
    rows = (
        db.query(ClientProfile, NatalChart)
        .outerjoin(NatalChart, ClientProfile.natal_chart_id == NatalChart.id)
        .filter(ClientProfile.astrologer_id == astrologer.id)
        .all()
    )

    result = []
    for client, chart in rows:
        if not chart:
            continue

        planets: list[dict] = chart.planets or []

        # Знак Солнца
        if sun_sign:
            sun = next((p for p in planets if p.get("name") == "Sun"), None)
            if not sun or sun.get("sign") != sun_sign:
                continue

        # Знак Луны
        if moon_sign:
            moon = next((p for p in planets if p.get("name") == "Moon"), None)
            if not moon or moon.get("sign") != moon_sign:
                continue

        # Знак Асцендента
        if asc_sign:
            asc = chart.ascendant or {}
            if asc.get("sign") != asc_sign:
                continue

        # Планета в конкретном доме
        if planet and house:
            target = next((p for p in planets if p.get("name") == planet), None)
            if not target or target.get("house") != house:
                continue
        elif planet:
            if not any(p.get("name") == planet for p in planets):
                continue
        elif house:
            if not any(p.get("house") == house for p in planets):
                continue

        result.append(client)

    return result


@router.get("/{client_id}", response_model=ClientOut)
async def get_client(
    client_id: int,
    user: User = _read,
    db: Session = Depends(get_db),
):
    astrologer = _get_astrologer(user, db)
    return _get_client_or_404(client_id, astrologer, db)


@router.patch("/{client_id}", response_model=ClientOut)
async def update_client(
    client_id: int,
    payload: ClientPatch,
    user: User = _write,
    db: Session = Depends(get_db),
):
    astrologer = _get_astrologer(user, db)
    client = _get_client_or_404(client_id, astrologer, db)
    if payload.notes is not None:
        client.notes = payload.notes
    if payload.name is not None:
        client.name = payload.name
    if payload.email is not None:
        client.email = payload.email
    if payload.status is not None:
        client.status = payload.status
    if payload.source is not None:
        client.source = payload.source
    if payload.tags is not None:
        client.tags = payload.tags
    if payload.natal_chart_id is not None:
        chart = db.query(NatalChart).filter(
            NatalChart.id == payload.natal_chart_id,
            NatalChart.user_id == user.id,
        ).first()
        if not chart:
            raise HTTPException(status_code=404, detail="Chart not found")
        client.natal_chart_id = payload.natal_chart_id
    db.commit()
    db.refresh(client)
    return client


@router.delete("/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_client(
    client_id: int,
    user: User = _write,
    db: Session = Depends(get_db),
):
    astrologer = _get_astrologer(user, db)
    client = _get_client_or_404(client_id, astrologer, db)
    db.delete(client)
    db.commit()


# ── Consultations (020) ──

@router.get("/{client_id}/consultations", response_model=list[ConsultationOut])
async def list_consultations(
    client_id: int,
    user: User = _read,
    db: Session = Depends(get_db),
):
    astrologer = _get_astrologer(user, db)
    client = _get_client_or_404(client_id, astrologer, db)
    return (
        db.query(Consultation)
        .filter(Consultation.client_id == client.id)
        .order_by(Consultation.date.desc())
        .all()
    )


@router.post("/{client_id}/consultations", response_model=ConsultationOut, status_code=status.HTTP_201_CREATED)
async def create_consultation(
    client_id: int,
    payload: ConsultationCreate,
    user: User = _write,
    db: Session = Depends(get_db),
):
    astrologer = _get_astrologer(user, db)
    client = _get_client_or_404(client_id, astrologer, db)
    consultation = Consultation(
        client_id=client.id,
        date=payload.date or datetime.utcnow(),
        topic=payload.topic,
        notes=payload.notes,
        assignment=payload.assignment,
        next_date=payload.next_date,
        price=payload.price,
        status=payload.status,
        question_moment=payload.question_moment,
        question_place=payload.question_place,
    )

    # Хорар: строим карту на момент вопроса (№17)
    if payload.topic in ("horary", "хорар") and payload.question_moment and payload.question_place:
        try:
            qm = payload.question_moment
            chart = await _geocode_and_build_chart(
                db, user_id=user.id,
                date_str=qm.strftime("%Y-%m-%d"), time_str=qm.strftime("%H:%M"),
                place=payload.question_place,
            )
            consultation.horary_chart_id = chart.id
        except Exception as e:
            logger.warning("Horary chart build failed: %s", e)

    db.add(consultation)
    db.commit()
    db.refresh(consultation)
    return consultation


@router.patch("/{client_id}/consultations/{consultation_id}", response_model=ConsultationOut)
async def update_consultation(
    client_id: int,
    consultation_id: int,
    payload: ConsultationPatch,
    user: User = _write,
    db: Session = Depends(get_db),
):
    astrologer = _get_astrologer(user, db)
    client = _get_client_or_404(client_id, astrologer, db)
    consultation = _get_consultation_or_404(consultation_id, client, db)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(consultation, field, value)
    db.commit()
    db.refresh(consultation)
    return consultation


@router.delete("/{client_id}/consultations/{consultation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_consultation(
    client_id: int,
    consultation_id: int,
    user: User = _write,
    db: Session = Depends(get_db),
):
    astrologer = _get_astrologer(user, db)
    client = _get_client_or_404(client_id, astrologer, db)
    consultation = _get_consultation_or_404(consultation_id, client, db)
    db.delete(consultation)
    db.commit()


# ── Brief to meeting (021 / roadmap idea 2) ──

@router.post("/{client_id}/brief")
async def generate_brief(
    client_id: int,
    user: User = _write,
    db: Session = Depends(get_db),
):
    """SSE-бриф к встрече: натальные акценты + активные транзиты (месяц вперёд)
    + прошлая консультация → единый custom_prompt через InterpretationRouter.
    Прогрессии не включены (движка прогрессий в проекте нет)."""
    from datetime import date as date_type, timedelta
    from backend.transit.engine import calculate_transits
    from backend.interpretation.base import InterpretationRequest
    from backend.interpretation.router import get_router
    from backend.crm.brief_prompt import build_brief_prompt
    from backend.crm.author_lib import author_context_for_chart

    astrologer = _get_astrologer(user, db)
    client = _get_client_or_404(client_id, astrologer, db)
    if not client.natal_chart_id:
        raise HTTPException(status_code=404, detail="Chart not calculated yet")
    chart = db.query(NatalChart).filter(NatalChart.id == client.natal_chart_id).first()
    if not chart:
        raise HTTPException(status_code=404, detail="Chart not found")

    author_ctx = author_context_for_chart(db, astrologer.id, chart.planets, chart.ascendant)

    profile = {
        "planets": chart.planets,
        "houses": chart.houses,
        "aspects": chart.aspects,
        "ascendant": chart.ascendant,
        "midheaven": chart.midheaven,
        "time_unknown": chart.time_unknown,
    }

    today = date_type.today()
    events = calculate_transits(
        natal_planets=chart.planets,
        from_date=today,
        to_date=today + timedelta(days=30),
    )
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

    last = (
        db.query(Consultation)
        .filter(Consultation.client_id == client.id)
        .order_by(Consultation.date.desc())
        .first()
    )
    last_consultation = (
        {"date": last.date, "topic": last.topic, "notes": last.notes} if last else None
    )

    birth_time = client.birth_time
    if hasattr(birth_time, "strftime"):
        birth_time = birth_time.strftime("%H:%M")
    birth_info = f"{client.birth_date}" + (f" {birth_time}" if birth_time else "") + f", {client.birth_place}"

    brief_prompt = build_brief_prompt(
        client_name=client.name,
        birth_info=birth_info,
        natal_profile=profile,
        transits=transit_dicts,
        last_consultation=last_consultation,
        author_context=author_ctx,
    )

    ai_router = get_router()

    async def event_stream():
        try:
            interp_request = InterpretationRequest(
                natal_profile=profile,
                context="transit",
                tier=user.tier,
                custom_prompt=brief_prompt,
            )
            for eng in ai_router._engines:
                if eng.name == "template":
                    continue
                if not ai_router._check_budget(eng.name):
                    continue
                try:
                    streamed = False
                    async for chunk in eng.stream(interp_request):
                        yield f"data: {json.dumps({'text': chunk}, ensure_ascii=False)}\n\n"
                        streamed = True
                    if streamed:
                        yield "data: [DONE]\n\n"
                        return
                except Exception as e:
                    logger.warning("Brief stream from %s failed: %s", eng.name, e)
                    continue

            yield f"data: {json.dumps({'text': 'AI временно недоступен. Попробуйте позже.'}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            logger.exception("Brief generation stream failed")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


# ── AI client summary (024 / roadmap idea 7) ──

def _summary_key(client: ClientProfile, consultations: list) -> str:
    parts = [str(client.natal_chart_id or ""), (client.notes or "")]
    for c in consultations:
        parts.append(f"{c.id}|{c.date}|{c.topic}|{c.notes}|{c.status}")
    return hashlib.sha256("\u0001".join(parts).encode("utf-8")).hexdigest()


@router.get("/{client_id}/summary")
async def client_summary(
    client_id: int,
    refresh: int = Query(0),
    user: User = _read,
    db: Session = Depends(get_db),
):
    """AI-портрет клиента (карта + заметки + консультации). Кэш на клиенте,
    инвалидация по хэшу заметок/консультаций/карты."""
    astrologer = _get_astrologer(user, db)
    client = _get_client_or_404(client_id, astrologer, db)

    consultations = (
        db.query(Consultation)
        .filter(Consultation.client_id == client.id)
        .order_by(Consultation.date.desc())
        .all()
    )
    key = _summary_key(client, consultations)

    if not refresh and client.summary and client.summary_key == key:
        return {"summary": client.summary, "cached": True}

    if not client.natal_chart_id:
        raise HTTPException(status_code=400, detail="Chart not calculated yet")
    chart = db.query(NatalChart).filter(NatalChart.id == client.natal_chart_id).first()
    if not chart:
        raise HTTPException(status_code=404, detail="Chart not found")

    from backend.interpretation.base import InterpretationRequest
    from backend.interpretation.router import get_router
    from backend.crm.summary_prompt import build_summary_prompt
    from backend.crm.author_lib import author_context_for_chart

    author_ctx = author_context_for_chart(db, astrologer.id, chart.planets, chart.ascendant)

    profile = {
        "planets": chart.planets, "houses": chart.houses, "aspects": chart.aspects,
        "ascendant": chart.ascendant, "midheaven": chart.midheaven, "time_unknown": chart.time_unknown,
    }
    birth_time = client.birth_time
    if hasattr(birth_time, "strftime"):
        birth_time = birth_time.strftime("%H:%M")
    birth_info = f"{client.birth_date}" + (f" {birth_time}" if birth_time else "") + f", {client.birth_place}"

    prompt = build_summary_prompt(
        client_name=client.name,
        birth_info=birth_info,
        natal_profile=profile,
        notes=client.notes or "",
        consultations=[
            {"date": c.date, "topic": c.topic, "notes": c.notes, "status": c.status}
            for c in consultations
        ],
        author_context=author_ctx,
    )

    try:
        req = InterpretationRequest(
            natal_profile=profile, context="transit", tier=user.tier, custom_prompt=prompt,
        )
        result = await get_router().generate(req)
        text = (result.content or "").strip()
    except Exception as e:
        logger.warning("Client summary generation failed for %s: %s", client.id, e)
        raise HTTPException(status_code=503, detail="AI временно недоступен")

    if text:
        client.summary = text
        client.summary_key = key
        db.commit()

    return {"summary": text, "cached": False}


# ── Client portal on/off (026 / roadmap idea 10) ──

_PORTAL_APP_URL = os.getenv("APP_URL", "https://astreatime.ru")


class PortalToggle(BaseModel):
    enabled: bool = True


def _portal_out(portal: ClientPortalAccess) -> dict:
    return {"enabled": portal.enabled, "token": portal.token, "url": f"{_PORTAL_APP_URL}/portal/{portal.token}"}


@router.get("/{client_id}/portal")
async def get_portal(client_id: int, user: User = _read, db: Session = Depends(get_db)):
    astrologer = _get_astrologer(user, db)
    client = _get_client_or_404(client_id, astrologer, db)
    portal = db.query(ClientPortalAccess).filter(ClientPortalAccess.client_id == client.id).first()
    if not portal:
        return {"enabled": False, "token": None, "url": None}
    return _portal_out(portal)


@router.post("/{client_id}/portal")
async def set_portal(
    client_id: int,
    payload: PortalToggle,
    user: User = _write,
    db: Session = Depends(get_db),
):
    astrologer = _get_astrologer(user, db)
    client = _get_client_or_404(client_id, astrologer, db)
    portal = db.query(ClientPortalAccess).filter(ClientPortalAccess.client_id == client.id).first()
    if not portal:
        portal = ClientPortalAccess(client_id=client.id, token=secrets.token_urlsafe(24), enabled=payload.enabled)
        db.add(portal)
    else:
        portal.enabled = payload.enabled
    db.commit()
    db.refresh(portal)
    return _portal_out(portal)


@router.get("/{client_id}/chart")
async def get_client_chart(
    client_id: int,
    user: User = _read,
    db: Session = Depends(get_db),
):
    astrologer = _get_astrologer(user, db)
    client = _get_client_or_404(client_id, astrologer, db)

    # Если карта ещё не посчитана — считаем сейчас
    if not client.natal_chart_id:
        try:
            from backend.ephemeris.geo import geocode_place, resolve_utc_datetime
            from backend.ephemeris.calculator import calculate_full_chart

            geo = await geocode_place(client.birth_place)
            birth_time_str = client.birth_time.strftime("%H:%M") if hasattr(client.birth_time, 'strftime') else client.birth_time
            utc_dt, time_unknown, _ = resolve_utc_datetime(
                birth_date=str(client.birth_date),
                birth_time=birth_time_str,
                timezone=geo.timezone,
            )
            (chart_data, aspects) = calculate_full_chart(
                utc_dt=utc_dt,
                latitude=geo.latitude,
                longitude=geo.longitude,
                house_system="placidus",
                time_unknown=time_unknown,
            )
            chart = NatalChart(
                user_id=user.id,
                birth_date=str(client.birth_date),
                birth_time=birth_time_str,
                birth_place=geo.display_name,
                latitude=geo.latitude,
                longitude=geo.longitude,
                timezone=geo.timezone,
                utc_datetime=utc_dt,
                time_unknown=time_unknown,
                house_system="placidus",
                planets=[{"name": p.name, "longitude": p.longitude, "sign": p.sign,
                          "degree_in_sign": p.degree_in_sign,
                          "house": p.house if not time_unknown else None,
                          "retrograde": p.retrograde} for p in chart_data.planets],
                houses=[{"number": h.number, "sign": h.sign, "degree": h.degree} for h in chart_data.houses],
                aspects=[{"planet1": a.planet1, "planet2": a.planet2, "aspect_type": a.aspect_type,
                          "angle": a.angle, "orb": a.orb, "applying": a.applying,
                          "importance": getattr(a, "importance", "low")} for a in aspects],
                ascendant={"sign": chart_data.ascendant.sign, "degree": chart_data.ascendant.degree,
                           "longitude": chart_data.ascendant.longitude} if chart_data.ascendant else None,
                midheaven={"sign": chart_data.midheaven.sign, "degree": chart_data.midheaven.degree,
                           "longitude": chart_data.midheaven.longitude} if chart_data.midheaven else None,
            )
            db.add(chart)
            db.commit()
            db.refresh(chart)
            client.natal_chart_id = chart.id
            db.commit()
            db.refresh(client)
        except Exception as e:
            logger.exception("On-demand chart calculation failed for client %s: %s", client_id, e)
            raise HTTPException(status_code=500, detail=f"Chart calculation failed: {e}")

    chart = db.query(NatalChart).filter(NatalChart.id == client.natal_chart_id).first()
    if not chart:
        raise HTTPException(status_code=404, detail="Chart not found")
    return {
        "id": chart.id,
        "planets": chart.planets,
        "houses": chart.houses,
        "aspects": chart.aspects,
        "ascendant": chart.ascendant,
        "midheaven": chart.midheaven,
    }


@router.get("/{client_id}/transits")
async def get_client_transits(
    client_id: int,
    from_date: date = Query(...),
    to_date: date = Query(...),
    user: User = _read,
    db: Session = Depends(get_db),
):
    astrologer = _get_astrologer(user, db)
    client = _get_client_or_404(client_id, astrologer, db)
    if not client.natal_chart_id:
        raise HTTPException(status_code=404, detail="Chart not calculated yet")
    chart = db.query(NatalChart).filter(NatalChart.id == client.natal_chart_id).first()
    if not chart:
        raise HTTPException(status_code=404, detail="Chart not found")
    from backend.transit.engine import calculate_transits
    events = calculate_transits(
        natal_planets=chart.planets,
        from_date=from_date,
        to_date=to_date,
    )
    return [
        {
            "transit_planet": e.transit_planet,
            "natal_planet": e.natal_planet,
            "aspect_type": e.aspect_type,
            "start_date": e.start_date,
            "peak_date": e.peak_date,
            "end_date": e.end_date,
            "peak_orb": e.peak_orb,
            "transit_sign": e.transit_sign,
        }
        for e in events
    ]


@router.post("/{client_id}/report")
async def generate_client_report(
    client_id: int,
    request: Request,
    user: User = _write,
    db: Session = Depends(get_db),
):
    import traceback as _tb
    from fastapi.responses import Response as FastAPIResponse
    try:
        # Читаем word_limit/wheel_png из тела запроса (опционально)
        word_limit = None
        wheel_png = None
        try:
            body = await request.json()
            wl = body.get("word_limit")
            if isinstance(wl, int) and 1000 <= wl <= 5000:
                word_limit = wl
            wp = body.get("wheel_png")
            if isinstance(wp, str) and wp:
                wheel_png = wp
        except Exception:
            pass

        astrologer = _get_astrologer(user, db)
        client = _get_client_or_404(client_id, astrologer, db)
        if not client.natal_chart_id:
            raise HTTPException(status_code=404, detail="Chart not calculated yet")

        chart = db.query(NatalChart).filter(NatalChart.id == client.natal_chart_id).first()
        if not chart:
            raise HTTPException(status_code=404, detail="Chart not found")

        astrologer_name = None
        profile = db.query(AstrologerProfile).filter(AstrologerProfile.user_id == user.id).first()
        if profile and profile.display_name:
            astrologer_name = profile.display_name

        # Генерируем интерпретацию для PDF
        interpretation_text = ""
        try:
            from backend.interpretation.base import InterpretationRequest
            from backend.interpretation.router import get_router as get_interp_router
            from backend.crm.author_lib import author_context_for_chart
            natal_profile = {
                "planets": chart.planets,
                "houses": chart.houses,
                "aspects": chart.aspects,
                "ascendant": chart.ascendant,
                "midheaven": chart.midheaven,
                "time_unknown": chart.time_unknown,
            }
            author_ctx = author_context_for_chart(db, astrologer.id, chart.planets, chart.ascendant)
            interp_req = InterpretationRequest(
                natal_profile=natal_profile,
                tier=user.tier,
                word_limit=word_limit,
                author_context=(author_ctx or None),
            )
            interp_router = get_interp_router()
            result = await interp_router.generate(interp_req)
            interpretation_text = result.content
        except Exception as e:
            logger.warning("Interpretation generation failed for PDF: %s", e)

        try:
            from backend.natal_pdf import generate_pdf_bytes
            pdf_bytes = generate_pdf_bytes(
                chart, interpretation=interpretation_text, astrologer_name=astrologer_name,
                wheel_png=wheel_png,
            )
        except Exception:
            logger.exception("natal_pdf failed, using simple fallback")
            pdf_bytes = _simple_pdf(chart, client, astrologer_name)

        import urllib.parse
        safe_name = f"natal_{chart.birth_date}.pdf"
        encoded_name = urllib.parse.quote(f"natal_{client.name}_{chart.birth_date}.pdf")
        return FastAPIResponse(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={safe_name}; filename*=UTF-8''{encoded_name}"},
        )
    except HTTPException:
        raise
    except Exception as e:
        detail = _tb.format_exc()
        logger.exception("generate_client_report failed: %s", e)
        raise HTTPException(status_code=500, detail=detail)


def _simple_pdf(chart, client, astrologer_name=None) -> bytes:
    """Minimal pure-Python PDF — no reportlab needed."""
    lines = [
        "НАТАЛЬНАЯ КАРТА",
        "=" * 50,
        f"Клиент:  {client.name}",
        f"Дата:    {chart.birth_date}",
        f"Время:   {chart.birth_time or 'неизвестно'}",
        f"Место:   {chart.birth_place}",
        f"Система: {chart.house_system or 'Placidus'}",
        "",
        "ПЛАНЕТЫ",
        "-" * 50,
    ]
    for p in (chart.planets or []):
        retro = " R" if p.get("retrograde") else ""
        house = f"  Дом {p['house']}" if p.get("house") else ""
        lines.append(f"  {p['name']:<12} {p['sign']:<14} {p.get('degree_in_sign', 0):.1f}°{house}{retro}")
    lines += ["", "ДОМА", "-" * 50]
    for h in (chart.houses or []):
        lines.append(f"  Дом {h['number']:2d}  {h['sign']}")
    lines += ["", "АСПЕКТЫ", "-" * 50]
    for a in (chart.aspects or [])[:30]:
        lines.append(f"  {a['planet1']:<12} {a['aspect_type']:<12} {a['planet2']:<12} орб {a.get('orb', 0):.1f}°")
    lines += ["", "-" * 50, astrologer_name or "Astrea Timeline · astreatime.ru"]

    text = "\n".join(lines)

    # Build minimal valid PDF
    objects = []

    def add(obj): objects.append(obj); return len(objects)

    catalog_id = add(None)
    pages_id   = add(None)
    font_id    = add(None)
    page_id    = add(None)
    stream_id  = add(None)

    # PDF stream content
    font_size = 10
    line_h = 14
    margin = 50
    page_w, page_h = 595, 842

    content_lines = []
    content_lines.append("BT")
    content_lines.append(f"/F1 {font_size} Tf")
    y = page_h - margin
    for line in lines:
        safe = line.encode("latin-1", errors="replace").decode("latin-1")
        safe = safe.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        content_lines.append(f"{margin} {y} Td" if y == page_h - margin else f"0 -{line_h} Td")
        content_lines.append(f"({safe}) Tj")
        y -= line_h
    content_lines.append("ET")
    stream_content = "\n".join(content_lines).encode("latin-1", errors="replace")

    # Build PDF bytes
    buf = b"%PDF-1.4\n"
    offsets = {}

    def write_obj(oid, content):
        nonlocal buf
        offsets[oid] = len(buf)
        buf += f"{oid} 0 obj\n".encode()
        buf += content
        buf += b"\nendobj\n"

    write_obj(catalog_id, f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode())
    write_obj(pages_id,   f"<< /Type /Pages /Kids [{page_id} 0 R] /Count 1 >>".encode())
    write_obj(font_id,    b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>")
    write_obj(page_id,    (
        f"<< /Type /Page /Parent {pages_id} 0 R "
        f"/MediaBox [0 0 {page_w} {page_h}] "
        f"/Contents {stream_id} 0 R "
        f"/Resources << /Font << /F1 {font_id} 0 R >> >> >>"
    ).encode())
    stream_bytes = stream_content
    write_obj(stream_id,  f"<< /Length {len(stream_bytes)} >>\nstream\n".encode() + stream_bytes + b"\nendstream")

    xref_offset = len(buf)
    buf += f"xref\n0 {len(offsets)+1}\n0000000000 65535 f \n".encode()
    for i in range(1, len(offsets) + 1):
        buf += f"{offsets[i]:010d} 00000 n \n".encode()
    buf += f"trailer\n<< /Size {len(offsets)+1} /Root {catalog_id} 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode()

    return buf
