"""Ручки первой недели (флаг first_week, backend/first_week.py).

GET  /api/v1/first-week       — карточка на сегодня (или null) и итог недели
POST /api/v1/first-week/seen  — отметка «функцию открыли»

Флаг выключен — обе 404 (docs/flags.md, п.3). Итог недели считает эфемериды
(main_event за 13 дней) — синхронно, поэтому через asyncio.to_thread
(backend/CLAUDE.md, Swiss Ephemeris).
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend import first_week
from backend.auth.dependencies import get_current_user
from backend.chart_utils import get_primary_chart
from backend.database import get_db
from backend.flags import flag_on
from backend.models import User

router = APIRouter(prefix="/api/v1/first-week", tags=["first-week"])


def _gate(db: Session, user: User) -> None:
    if not flag_on(db, first_week.FLAG, user):
        raise HTTPException(status_code=404)


@router.get("")
async def get_card(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _gate(db, user)
    chart = get_primary_chart(db, user)
    if not chart:
        return {"card": None}
    return {"card": await asyncio.to_thread(first_week.card, db, user, chart)}


class SeenIn(BaseModel):
    key: str


@router.post("/seen")
def post_seen(body: SeenIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _gate(db, user)
    if body.key not in first_week.KEYS:
        raise HTTPException(status_code=422, detail="unknown key")
    first_week.mark(db, user, body.key)
    return {"ok": True}
