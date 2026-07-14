"""backend/exit_survey/router.py — E10 exit-survey (3 момента).

GET  /api/v1/exit-survey/reasons   — список причин для фронта (публично)
POST /api/v1/exit-survey           — сохранить причину (auth опционально)
GET  /api/v1/exit-survey/summary   — сводка для админа (require_admin)

Три момента (поле moment):
  active       — активный уход (модалка перед DELETE /auth/me или отключением)
  dormant      — переход по ссылке из письма спящего (день 10/14)
  end_of_month — конец месяца без продолжения (письмо после даунгрейда)

Атрибуция user_id: если запрос авторизован — берём реального пользователя
(get_current_user_optional). Для ссылок из писем (юзер может быть не залогинен)
фолбэк на payload.user_id из параметра ?u=<id>.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import ExitReason, User
from backend.auth.dependencies import get_current_user_optional
from backend.admin.admin_router import require_admin
from backend.metrics import log_event

logger = logging.getLogger("astro.exit")

router = APIRouter(prefix="/api/v1/exit-survey", tags=["exit-survey"])

# Причины: частые первыми, фрейминг «помогите улучшить». Последняя — other.
REASONS = [
    {"code": "onboarding", "label": "Не понял, как пользоваться"},
    {"code": "no_value",   "label": "Не увидел пользы для себя"},
    {"code": "price",      "label": "Дорого"},
    {"code": "depth",      "label": "Не хватило точности или глубины"},
    {"code": "tech",       "label": "Технические проблемы"},
    {"code": "curiosity",  "label": "Просто пробовал из любопытства"},
    {"code": "other",      "label": "Другое"},
]
_VALID_CODES = {r["code"] for r in REASONS}
_VALID_MOMENTS = {"active", "dormant", "end_of_month"}


class ExitIn(BaseModel):
    moment: str = "active"
    reason_code: Optional[str] = None
    reason_text: Optional[str] = None
    user_id: Optional[str] = None   # фолбэк для ссылок из писем (?u=<id>)


@router.get("/reasons")
async def get_reasons():
    return {"reasons": REASONS}


@router.post("")
async def submit_exit(
    payload: ExitIn,
    user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    uid = user.id if user else (payload.user_id or None)
    moment = payload.moment if payload.moment in _VALID_MOMENTS else "active"
    code = payload.reason_code if payload.reason_code in _VALID_CODES else None
    row = ExitReason(
        user_id=uid,
        moment=moment,
        reason_code=code,
        reason_text=(payload.reason_text or None),
    )
    db.add(row)
    db.commit()
    log_event(db, uid, "exit_reason", {"moment": moment, "code": code})
    return {"status": "ok"}


@router.get("/summary")
async def exit_summary(db: Session = Depends(get_db), _=Depends(require_admin)):
    """Причины ухода по коду и по моменту — метрики группы 4."""
    by_code = dict(
        db.query(ExitReason.reason_code, func.count(ExitReason.id))
        .group_by(ExitReason.reason_code).all()
    )
    by_moment = dict(
        db.query(ExitReason.moment, func.count(ExitReason.id))
        .group_by(ExitReason.moment).all()
    )
    total = db.query(func.count(ExitReason.id)).scalar() or 0
    return {"total": total, "by_code": by_code, "by_moment": by_moment}
