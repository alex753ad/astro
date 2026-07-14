"""backend/crm/access_router.py — E9 режим доступа к CRM для фронта.

GET /api/v1/crm/access → {"mode": "full" | "readonly" | "none",
                          "pilot_ended": <iso|null>}

Фронт по mode:
  full     — обычный CRM.
  readonly — баннер «только просмотр» + все action-кнопки заблокированы (замки).
  none     — CRM недоступен.
"""
from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import User
from backend.auth.dependencies import get_current_user
from backend.crm.access import access_mode, PILOT_DAYS

router = APIRouter(prefix="/api/v1/crm", tags=["crm"])


@router.get("/access")
async def get_crm_access(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    mode = access_mode(user)
    pilot_ended = None
    if getattr(user, "pilot_started_at", None):
        end = user.pilot_started_at + timedelta(days=PILOT_DAYS)
        pilot_ended = end.isoformat()
    return {"mode": mode, "pilot_ended": pilot_ended}
