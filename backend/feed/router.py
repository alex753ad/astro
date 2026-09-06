"""backend/feed/router.py — единая лента событий.

Существующие /transits, /planner/monthly и /calendar/lunar не трогаются: веб
работает на них, лента — отдельная ручка поверх тех же расчётов. Вся сборка
в builder.py, здесь только доступ, окно и тарифный горизонт.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from backend.auth.dependencies import get_current_user_optional
from backend.database import get_db
from backend.feed.builder import build_feed
from backend.limiter import limiter
from backend.models import NatalChart, User

logger = logging.getLogger("astro.feed")

router = APIRouter(prefix="/api/v1", tags=["feed"])

# Тот же потолок, что у /transits: расчёт эфемерид на длинном окне стоит
# секунды CPU, и ограничение стоит там же, где сам расчёт.
MAX_WINDOW_DAYS = 366


def _load_chart(chart_id: str, user: User | None, request: Request, db: Session) -> NatalChart:
    """Карта по id с проверкой доступа.

    Импорт отложенный: backend.main подключает этот роутер, поэтому импорт на
    уровне модуля дал бы цикл. Тот же приём, что в advanced_charts_router.
    """
    from backend.main import chart_token, resolve_chart_access

    return resolve_chart_access(chart_id, user, chart_token(request), db)


@router.get("/chart/{chart_id}/feed", summary="Лента событий за произвольное окно")
@limiter.limit("30/minute")
async def get_feed(
    request: Request,
    chart_id: str,
    from_date: str,
    to_date: str,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    """Транзиты, периоды планера и лунные события одним ответом.

    Окно произвольное — две даты, без привязки к календарному месяцу.
    Внутри планер считается по датам напрямую, month_offset наружу не
    протекает.
    """
    try:
        from_dt = date.fromisoformat(from_date)
        to_dt = date.fromisoformat(to_date)
    except ValueError:
        raise HTTPException(status_code=422, detail="Неверный формат даты. Ожидается YYYY-MM-DD.")

    if to_dt < from_dt:
        raise HTTPException(status_code=422, detail="to_date не может быть раньше from_date.")
    if (to_dt - from_dt).days > MAX_WINDOW_DAYS:
        raise HTTPException(
            status_code=422,
            detail=f"Окно ленты не может превышать {MAX_WINDOW_DAYS} дней.",
        )

    chart = _load_chart(chart_id, user, request, db)
    tier = user.tier if user else "free"

    # 403 за горизонтом здесь НЕТ намеренно, в отличие от /transits.
    # Лента листается, и упереться в край — обычное её состояние, а не ошибка:
    # build_feed обрезает окно горизонтом и возвращает границу вместе с тем,
    # что открывается на следующем тарифе (backend/feed/horizon.py). На 403
    # фронту пришлось бы гадать, где именно край и чем его подписать.

    # build_feed синхронный и считает эфемериды — из async-обработчика только
    # через to_thread, иначе он держит единственный event loop процесса
    # (правило из CLAUDE.md, раздел про Swiss Ephemeris).
    return await asyncio.to_thread(
        build_feed,
        chart=chart,
        from_date=from_dt,
        to_date=to_dt,
        today=date.today(),
        tier=tier,
    )
