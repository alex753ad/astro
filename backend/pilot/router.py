"""backend/pilot/router.py — вход в пилот через Telegram.

Публичный:
  POST /api/v1/pilot/claim   { "token": "<one-time>" }   (auth: залогинен по почте)
     → ставит pilot_started_at=now(), tier=premium, привязывает tg_user_id.

Internal (для бота, заголовок X-Internal-Secret):
  POST /api/v1/internal/pilot-token   { "tg_user_id": "..." }
     → выпускает одноразовую ссылку /pilot/claim?t=<token> (TTL 60 мин).

Анти-абуз: один пилот на веб-аккаунт (pilot_started_at) И один на tg-аккаунт
(tg_user_id + использованные токены). Промокодного входа больше нет.
"""
from __future__ import annotations

import logging
import os
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.config import get_settings
from backend.models import User, PilotToken
from backend.auth.dependencies import get_current_user
from backend.metrics import log_event, EventName

logger = logging.getLogger("astro.pilot")

router = APIRouter(prefix="/api/v1", tags=["pilot"])

PILOT_DAYS = int(os.getenv("PILOT_DAYS", "30"))
TOKEN_TTL_MIN = int(os.getenv("PILOT_TOKEN_TTL_MIN", "60"))


# ── Internal: выпуск токена ботом ──
class TokenIssueIn(BaseModel):
    tg_user_id: str


def _tg_already_piloted(db: Session, tg_user_id: str) -> bool:
    """tg-аккаунт уже активировал пилот (привязан к юзеру ИЛИ есть погашенный токен)."""
    if db.query(User.id).filter(
        User.tg_user_id == tg_user_id, User.pilot_started_at.isnot(None)
    ).first():
        return True
    if db.query(PilotToken.id).filter(
        PilotToken.tg_user_id == tg_user_id, PilotToken.used.is_(True)
    ).first():
        return True
    return False


@router.post("/internal/pilot-token")
async def issue_pilot_token(
    payload: TokenIssueIn,
    x_internal_secret: str = Header(default=""),
    db: Session = Depends(get_db),
):
    secret = os.getenv("INTERNAL_SECRET", "")
    if secret and x_internal_secret != secret:
        raise HTTPException(status_code=403, detail="Forbidden")

    tg_id = (payload.tg_user_id or "").strip()
    if not tg_id:
        raise HTTPException(status_code=400, detail="tg_user_id required")

    if _tg_already_piloted(db, tg_id):
        raise HTTPException(status_code=409, detail="already_claimed")

    token = secrets.token_urlsafe(24)
    expires = datetime.utcnow() + timedelta(minutes=TOKEN_TTL_MIN)
    db.add(PilotToken(token=token, tg_user_id=tg_id, expires_at=expires))
    db.commit()

    frontend = get_settings().frontend_url.rstrip("/")
    return {
        "token": token,
        "claim_url": f"{frontend}/pilot/claim?t={token}",
        "expires_at": expires.isoformat(),
    }


# ── Public: активация по токену ──
class ClaimIn(BaseModel):
    token: str


@router.post("/pilot/claim")
async def claim_pilot(
    payload: ClaimIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = db.query(PilotToken).filter(PilotToken.token == payload.token).first()
    if not row:
        raise HTTPException(status_code=404, detail="invalid_token")
    if row.used:
        raise HTTPException(status_code=409, detail="token_used")
    if row.expires_at < datetime.utcnow():
        raise HTTPException(status_code=410, detail="token_expired")

    # веб-аккаунт уже был в пилоте?
    if user.pilot_started_at is not None:
        raise HTTPException(status_code=409, detail="already_pilot")

    # tg-аккаунт уже привязан к другому юзеру с пилотом?
    other = db.query(User.id).filter(
        User.tg_user_id == row.tg_user_id,
        User.pilot_started_at.isnot(None),
        User.id != user.id,
    ).first()
    if other:
        raise HTTPException(status_code=409, detail="tg_already_used")

    now = datetime.utcnow()
    user.pilot_started_at = now
    user.tier = "premium"
    user.tg_user_id = row.tg_user_id
    row.used = True
    row.used_by_user_id = user.id
    db.add(user)
    db.add(row)
    db.commit()
    db.refresh(user)

    log_event(db, user.id, EventName.PROMO_ACTIVATED,
              {"kind": "pilot_telegram", "tg_user_id": row.tg_user_id})

    return {
        "status": "ok",
        "tier": user.tier,
        "pilot_started_at": now.isoformat(),
        "pilot_days": PILOT_DAYS,
    }
