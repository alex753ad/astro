"""GET /api/v1/widget — запас дней для виджета «День» (флаг widget,
backend/widget.py).

Флаг выключен — 404 (docs/flags.md, п.3): приложение по этому ответу запас
не кладёт. Нет карты — пустой список, виджет покажет одну Луну.
"""
from __future__ import annotations

import asyncio
from datetime import datetime

import pytz
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend import widget
from backend.auth.dependencies import get_current_user
from backend.chart_utils import get_primary_chart
from backend.database import get_db
from backend.flags import flag_on
from backend.models import User

router = APIRouter(prefix="/api/v1/widget", tags=["widget"])


@router.get("")
async def get_days(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not flag_on(db, widget.FLAG, user):
        raise HTTPException(status_code=404)
    chart = get_primary_chart(db, user)
    if not chart:
        return {"days": []}
    from backend.push.cron import user_timezone
    today = datetime.now(pytz.timezone(user_timezone(user, chart))).date()
    return {"days": await asyncio.to_thread(widget.days, user, chart, today)}
