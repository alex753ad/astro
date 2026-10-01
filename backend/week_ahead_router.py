"""GET /api/v1/week-ahead — карточка «Недели вперёд» (флаг week_ahead,
backend/week_ahead.py) или null.

Флаг выключен — 404 (docs/flags.md, п.3). Отбор считает эфемериды (main_event
за 7 дней) — синхронно, поэтому через asyncio.to_thread (backend/CLAUDE.md,
Swiss Ephemeris).
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend import week_ahead
from backend.auth.dependencies import get_current_user
from backend.chart_utils import get_primary_chart
from backend.database import get_db
from backend.flags import flag_on
from backend.models import User

router = APIRouter(prefix="/api/v1/week-ahead", tags=["week-ahead"])


@router.get("")
async def get_card(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not flag_on(db, week_ahead.FLAG, user):
        raise HTTPException(status_code=404)
    chart = get_primary_chart(db, user)
    if not chart:
        return {"card": None}
    return {"card": await asyncio.to_thread(week_ahead.card, db, user, chart)}
