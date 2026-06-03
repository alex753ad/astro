"""backend/calendar/export_router.py
Логирование экспорта событий в Google Calendar.

POST /api/v1/calendar/export-log
  — принимает результат экспорта с фронтенда
  — сохраняет в calendar_export_logs
  — требует авторизации (JWT)
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
    )
    db.add(entry)
    db.commit()
    return {"ok": True}
