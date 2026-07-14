"""backend/feedback/router.py — E8 «Здесь что-то не так».

POST /api/v1/feedback        — создать запись (auth: любой залогиненный)
GET  /api/v1/feedback        — список для админа (require_admin)

Подключить в main.py: app.include_router(feedback_router).
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Feedback, User
from backend.auth.dependencies import get_current_user
from backend.admin.admin_router import require_admin
from backend.metrics import log_event  # для метрик трения (E11)

logger = logging.getLogger("astro.feedback")

router = APIRouter(prefix="/api/v1/feedback", tags=["feedback"])


class FeedbackIn(BaseModel):
    screen: Optional[str] = None
    url: Optional[str] = None
    message: Optional[str] = None


class FeedbackOut(BaseModel):
    id: int
    screen: Optional[str] = None
    url: Optional[str] = None
    message: Optional[str] = None

    model_config = {"from_attributes": True}


@router.post("", response_model=FeedbackOut, status_code=201)
async def create_feedback(
    payload: FeedbackIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = Feedback(
        user_id=user.id,
        screen=(payload.screen or "")[:120] or None,
        url=(payload.url or "")[:500] or None,
        message=payload.message,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    # событие трения — считаем, где чаще всего жмут «что-то не так»
    log_event(db, user.id, "feedback_reported", {"screen": row.screen})
    return row


@router.get("", response_model=list[FeedbackOut])
async def list_feedback(db: Session = Depends(get_db), _=Depends(require_admin)):
    return db.query(Feedback).order_by(Feedback.created_at.desc()).limit(200).all()
