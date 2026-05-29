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
from pydantic import BaseModel
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

    class Config:
        from_attributes = True


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
    if not client.natal_chart_id:
        raise HTTPException(status_code=404, detail="Chart not calculated yet")
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
    # Delegate to existing transit logic
    from backend.transit.engine import get_transits_for_chart
    chart = db.query(NatalChart).filter(NatalChart.id == client.natal_chart_id).first()
    return get_transits_for_chart(chart, str(from_date), str(to_date))


@router.post("/{client_id}/report", status_code=status.HTTP_202_ACCEPTED)
async def generate_client_report(
    client_id: int,
    user: User = _premium,
    db: Session = Depends(get_db),
):
    astrologer = _get_astrologer(user, db)
    client = _get_client_or_404(client_id, astrologer, db)
    if not client.natal_chart_id:
        raise HTTPException(status_code=404, detail="Chart not calculated yet")
    from backend.tasks import generate_pdf_report
    task = generate_pdf_report.delay(client.natal_chart_id, user.id)
    return {"task_id": task.id, "status": "queued"}
