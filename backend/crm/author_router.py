"""Author interpretations CRUD (roadmap idea 13).

/api/v1/astrologer/interpretations — личная база «моих» трактовок.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import AstrologerInterpretation, AstrologerProfile, User
from backend.auth.dependencies import require_tier

logger = logging.getLogger("astro.author")

router = APIRouter(prefix="/api/v1/astrologer", tags=["author"])

_premium = Depends(require_tier("premium"))


class AuthorInterpIn(BaseModel):
    key: str
    content: str


class AuthorInterpOut(BaseModel):
    id: int
    key: str
    content: str

    model_config = {"from_attributes": True}


def _astrologer(user: User, db: Session) -> AstrologerProfile:
    a = db.query(AstrologerProfile).filter(AstrologerProfile.user_id == user.id).first()
    if not a:
        a = AstrologerProfile(user_id=user.id, display_name=user.name or user.email)
        db.add(a)
        db.commit()
        db.refresh(a)
    return a


@router.get("/interpretations", response_model=list[AuthorInterpOut])
async def list_interpretations(user: User = _premium, db: Session = Depends(get_db)):
    a = _astrologer(user, db)
    return (
        db.query(AstrologerInterpretation)
        .filter(AstrologerInterpretation.astrologer_id == a.id)
        .order_by(AstrologerInterpretation.key.asc())
        .all()
    )


@router.post("/interpretations", response_model=AuthorInterpOut)
async def upsert_interpretation(payload: AuthorInterpIn, user: User = _premium, db: Session = Depends(get_db)):
    a = _astrologer(user, db)
    key = payload.key.strip().lower()
    if not key or not payload.content.strip():
        raise HTTPException(status_code=400, detail="key и content обязательны")
    row = db.query(AstrologerInterpretation).filter(
        AstrologerInterpretation.astrologer_id == a.id,
        AstrologerInterpretation.key == key,
    ).first()
    if row:
        row.content = payload.content
    else:
        row = AstrologerInterpretation(astrologer_id=a.id, key=key, content=payload.content)
        db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.patch("/interpretations/{interp_id}", response_model=AuthorInterpOut)
async def update_interpretation(
    interp_id: int,
    payload: AuthorInterpIn,
    user: User = _premium,
    db: Session = Depends(get_db),
):
    a = _astrologer(user, db)
    row = db.query(AstrologerInterpretation).filter(
        AstrologerInterpretation.id == interp_id,
        AstrologerInterpretation.astrologer_id == a.id,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    row.key = payload.key.strip().lower()
    row.content = payload.content
    db.commit()
    db.refresh(row)
    return row


@router.delete("/interpretations/{interp_id}", status_code=204)
async def delete_interpretation(interp_id: int, user: User = _premium, db: Session = Depends(get_db)):
    a = _astrologer(user, db)
    row = db.query(AstrologerInterpretation).filter(
        AstrologerInterpretation.id == interp_id,
        AstrologerInterpretation.astrologer_id == a.id,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(row)
    db.commit()
