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

import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import AstrologerProfile, ClientProfile, NatalChart, User
from backend.auth.dependencies import get_current_user, require_tier

logger = logging.getLogger("astro.crm")

router = APIRouter(prefix="/api/v1/clients", tags=["crm"])

_premium = Depends(require_tier("premium"))


# ── Schemas ──

class ClientCreate(BaseModel):
    name: str
    birth_date: date
    birth_time: Optional[str] = None
    birth_place: str
    notes: Optional[str] = None


class ClientPatch(BaseModel):
    notes: Optional[str] = None
    name: Optional[str] = None


class ClientOut(BaseModel):
    id: int
    name: str
    birth_date: date
    birth_time: Optional[str] = None
    birth_place: str
    notes: Optional[str] = None
    natal_chart_id: Optional[str] = None

    model_config = {"from_attributes": True}

    @field_validator("birth_time", mode="before")
    @classmethod
    def coerce_time(cls, v):
        import datetime
        if isinstance(v, datetime.time):
            return v.strftime("%H:%M")
        return v


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


# ── Endpoints ──

@router.post("", response_model=ClientOut, status_code=status.HTTP_201_CREATED)
async def create_client(
    payload: ClientCreate,
    user: User = _premium,
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
    )
    db.add(client)
    db.commit()
    db.refresh(client)

    # Автоматически считаем натальную карту
    try:
        from backend.ephemeris.geo import geocode_place, resolve_utc_datetime
        from backend.ephemeris.calculator import calculate_full_chart

        geo = await geocode_place(payload.birth_place)
        utc_dt, time_unknown, _ = resolve_utc_datetime(
            birth_date=str(payload.birth_date),
            birth_time=payload.birth_time,
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
            birth_date=str(payload.birth_date),
            birth_time=payload.birth_time,
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

        client.natal_chart_id = chart.id
        db.commit()
        db.refresh(client)
    except Exception as e:
        logger.warning("Auto chart calculation failed for client %s: %s", client.id, e)

    return client


@router.get("", response_model=list[ClientOut])
async def list_clients(
    q: Optional[str] = Query(None),
    user: User = _premium,
    db: Session = Depends(get_db),
):
    astrologer = _get_astrologer(user, db)
    query = db.query(ClientProfile).filter(ClientProfile.astrologer_id == astrologer.id)
    if q:
        query = query.filter(ClientProfile.name.ilike(f"%{q}%"))
    return query.order_by(ClientProfile.created_at.desc()).all()


@router.get("/{client_id}", response_model=ClientOut)
async def get_client(
    client_id: int,
    user: User = _premium,
    db: Session = Depends(get_db),
):
    astrologer = _get_astrologer(user, db)
    return _get_client_or_404(client_id, astrologer, db)


@router.patch("/{client_id}", response_model=ClientOut)
async def update_client(
    client_id: int,
    payload: ClientPatch,
    user: User = _premium,
    db: Session = Depends(get_db),
):
    astrologer = _get_astrologer(user, db)
    client = _get_client_or_404(client_id, astrologer, db)
    if payload.notes is not None:
        client.notes = payload.notes
    if payload.name is not None:
        client.name = payload.name
    db.commit()
    db.refresh(client)
    return client


@router.delete("/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_client(
    client_id: int,
    user: User = _premium,
    db: Session = Depends(get_db),
):
    astrologer = _get_astrologer(user, db)
    client = _get_client_or_404(client_id, astrologer, db)
    db.delete(client)
    db.commit()


@router.get("/{client_id}/chart")
async def get_client_chart(
    client_id: int,
    user: User = _premium,
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
            utc_dt, time_unknown, _ = resolve_utc_datetime(
                birth_date=str(client.birth_date),
                birth_time=client.birth_time.strftime('%H:%M') if client.birth_time else None,
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
                birth_time=client.birth_time.strftime('%H:%M') if client.birth_time else None,
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
    }


@router.get("/{client_id}/transits")
async def get_client_transits(
    client_id: int,
    from_date: date = Query(...),
    to_date: date = Query(...),
    user: User = _premium,
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
    user: User = _premium,
    db: Session = Depends(get_db),
):
    import traceback as _tb
    from fastapi.responses import Response as FastAPIResponse
    try:
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

        try:
            from backend.natal_pdf import generate_pdf_bytes
            pdf_bytes = generate_pdf_bytes(chart, astrologer_name=astrologer_name)
        except Exception:
            logger.warning("natal_pdf failed, using simple fallback")
            pdf_bytes = _simple_pdf(chart, client, astrologer_name)

        filename = f"natal_{client.name.replace(' ', '_')}_{chart.birth_date}.pdf"
        return FastAPIResponse(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
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
