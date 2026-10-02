"""Виджет «День» (флаг widget, backend/widget.py).

  GET  /api/v1/widget        — запас дней и «идёт ли первая неделя»
  POST /api/v1/widget/event  {"kind": "shown"|"added", "source": …} — сводка

Флаг выключен — 404 (docs/flags.md, п.3): приложение по этому ответу запас
не кладёт. Нет карты — пустой список, виджет покажет одну Луну.
"""
from __future__ import annotations

import asyncio
from datetime import datetime

import pytz
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend import widget
from backend.auth.dependencies import get_current_user
from backend.chart_utils import get_primary_chart
from backend.database import get_db
from backend.flags import flag_on
from backend.models import User, WidgetEvent

router = APIRouter(prefix="/api/v1/widget", tags=["widget"])


@router.get("")
async def get_days(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not flag_on(db, widget.FLAG, user):
        raise HTTPException(status_code=404)
    chart = get_primary_chart(db, user)
    if not chart:
        return {"days": [], "first_week": False}
    from backend import first_week
    from backend.push.cron import user_timezone
    today = datetime.now(pytz.timezone(user_timezone(user, chart))).date()
    # Идёт первая неделя (флаг first_week) — её роль играет день 3, карточку
    # «Добавь виджет» в ленте приложение не показывает (widgetPin.js).
    in_week = flag_on(db, first_week.FLAG, user) and first_week.day_number(user, chart, today) is not None
    return {"days": await asyncio.to_thread(widget.days, user, chart, today), "first_week": in_week}


class EventIn(BaseModel):
    kind: str
    source: str


@router.post("/event", status_code=204)
def post_event(data: EventIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not flag_on(db, widget.FLAG, user):
        raise HTTPException(status_code=404)
    if data.kind not in widget.EVENT_KINDS or data.source not in widget.EVENT_SOURCES:
        raise HTTPException(status_code=422, detail="kind: shown|added, source: first_week|card|manual")
    db.add(WidgetEvent(user_id=user.id, kind=data.kind, source=data.source))
    db.commit()
