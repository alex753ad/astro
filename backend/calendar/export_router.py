"""backend/calendar/export_router.py
Логирование экспорта событий в Google Calendar.

POST /api/v1/calendar/export-log
  — принимает результат экспорта с фронтенда
  — сохраняет в calendar_export_logs
  — требует авторизации (JWT)

GET /api/v1/calendar/export-allowed?chart_id=…
  — можно ли выгрузить эту карту на тарифе человека (TIER_FLAGS gcal_charts:
    Вега — одна карта, Лира и Орион — все). Экспорт идёт из браузера прямо в
    Google, поэтому сервер решает только «можно ли», а клиент обязан спросить
    до выгрузки (PlannerPage.useGcalExport).
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.auth.dependencies import get_current_user
from backend.database import get_db
from backend.models import CalendarExportLog, User

router = APIRouter(prefix="/api/v1/calendar", tags=["calendar"])


class ExportLogRequest(BaseModel):
    month: str                   # "YYYY-MM"
    event_count: int
    event_types: list[str]       # ["new_moon", "full_moon", "ingress", "aspect"]
    status: str                  # "success" | "error"
    error_msg: str | None = None
    chart_id: str | None = None  # какую карту выгрузили (066)


@router.post("/export-log", status_code=201)
def log_calendar_export(
    body: ExportLogRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Валидация month
    try:
        datetime.strptime(body.month, "%Y-%m")
    except ValueError:
        raise HTTPException(status_code=422, detail="Формат month: YYYY-MM")

    if body.status not in ("success", "error"):
        raise HTTPException(status_code=422, detail="status: 'success' или 'error'")

    entry = CalendarExportLog(
        user_id     = user.id,
        month       = body.month,
        event_count = body.event_count,
        event_types = body.event_types,
        status      = body.status,
        error_msg   = body.error_msg,
        chart_id    = (body.chart_id or "")[:36] or None,
    )
    db.add(entry)
    db.commit()
    return {"ok": True}


@router.get("/export-allowed")
def calendar_export_allowed(
    chart_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """{"allowed": bool, "reason": str|None}. Лимит — число РАЗНЫХ карт с
    успешным экспортом; повторная выгрузка той же карты разрешена всегда."""
    from backend.auth.rate_limits import TIER_FLAGS
    from backend.email_service import TIER_NAMES

    limit = TIER_FLAGS.get(user.tier, TIER_FLAGS["free"]).get("gcal_charts", 0)
    if limit is None:
        return {"allowed": True, "reason": None}
    if limit == 0:
        return {"allowed": False,
                "reason": f"Экспорт в Google Календарь — на тарифе {TIER_NAMES['lite']} и выше."}
    used = {
        cid for (cid,) in db.query(CalendarExportLog.chart_id)
        .filter(CalendarExportLog.user_id == user.id,
                CalendarExportLog.status == "success",
                CalendarExportLog.chart_id.isnot(None))
        .distinct()
    }
    if chart_id in used or len(used) < limit:
        return {"allowed": True, "reason": None}
    return {"allowed": False,
            "reason": (f"На тарифе {TIER_NAMES[user.tier]} экспорт — для одной карты, "
                       f"она уже выбрана. Для всех карт — {TIER_NAMES['pro']}.")}
