"""Карточка дня для сторис (флаг story_card, backend/story_card.py).

  GET  /api/v1/chart/{id}/story-card?date=YYYY-MM-DD — что написать на картинке
  POST /api/v1/story-card/shared {"variant": "chart"|"photo"} — счётчик отправок

Флаг выключен — 404 (docs/flags.md, п.3). Только с входом: гость прогноз в
ленте видит, но кнопки у него нет — отправка считается по аккаунту.
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend import story_card
from backend.auth.dependencies import get_current_user
from backend.database import get_db
from backend.flags import flag_on
from backend.models import StoryCardShare, User

router = APIRouter(prefix="/api/v1", tags=["story-card"])


@router.get("/chart/{chart_id}/story-card")
async def get_card(
    chart_id: str,
    day: date = Query(..., alias="date"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not flag_on(db, story_card.FLAG, user):
        raise HTTPException(status_code=404)
    from backend.main import resolve_chart_access   # отложенно: main подключает этот роутер
    from backend.time_utils import local_today, user_tz
    chart = resolve_chart_access(chart_id, user, None, db)
    # Вчера/сегодня/завтра по поясу человека: кнопка стоит на карточке
    # прогноза «сегодня», а сутки устройства и сервера могут не совпадать.
    # Шире не пускаем — каждый запрос считает эфемериды.
    today = local_today(user_tz(None, user, chart))
    if abs((day - today).days) > 1:
        raise HTTPException(status_code=422, detail="Карточка есть только на сегодня.")
    return await asyncio.to_thread(story_card.card, user, chart, day)


class SharedIn(BaseModel):
    variant: str


@router.post("/story-card/shared", status_code=204)
def shared(data: SharedIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Строка на каждую отправку, когда системный лист закрылся выбором
    получателя (отмена не считается). Сводка — metrics.retention_summary_text."""
    if not flag_on(db, story_card.FLAG, user):
        raise HTTPException(status_code=404)
    if data.variant not in story_card.VARIANTS:
        raise HTTPException(status_code=422, detail="Вариант: chart или photo.")
    db.add(StoryCardShare(user_id=user.id, variant=data.variant))
    db.commit()


def shares_since(db: Session, since: datetime) -> dict[str, int]:
    from sqlalchemy import func
    rows = (db.query(StoryCardShare.variant, func.count())
            .filter(StoryCardShare.created_at >= since)
            .group_by(StoryCardShare.variant).all())
    return {v: n for v, n in rows}

