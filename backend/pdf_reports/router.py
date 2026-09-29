"""Ручки PDF-отчётов (сборка в фоне, 29.09.2026).

POST /chart/{id}/pdf-reports    — начать сборку (или вернуть идущую/готовую)
GET  /chart/{id}/pdf-reports    — список «PDF-отчёты» в карточке карты
GET  /pdf-reports/{id}          — статус и прогресс
GET  /pdf-reports/{id}/file     — сам файл

Старый синхронный POST /chart/{id}/pdf (main.py) остаётся для старых APK:
они шлют его и ждут байты в ответе.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.auth.dependencies import get_current_user
from backend.database import get_db
from backend.limiter import limiter
from backend.models import NatalChart, PdfReport, User
from backend.pdf_reports.build import ACTIVE, FAIL_TEXT, start
from backend.time_utils import utcnow

router = APIRouter(prefix="/api/v1", tags=["pdf"])

TIER_NAMES = {"free": "Бесплатный", "lite": "Вега", "pro": "Лира", "premium": "Орион"}


class PdfStart(BaseModel):
    wheel_png: str | None = None  # base64 PNG колеса с сайта; нет — векторное


def _own_chart(db: Session, chart_id: str, user: User) -> NatalChart:
    chart = db.get(NatalChart, chart_id)
    # Чужая и анонимная — одинаково 404: отчёт живёт только у карты аккаунта.
    if chart is None or chart.user_id != user.id:
        raise HTTPException(status_code=404, detail="Карта не найдена")
    return chart


def _own_report(db: Session, report_id: str, user: User) -> PdfReport:
    r = db.get(PdfReport, report_id)
    if r is None or r.user_id != user.id:
        raise HTTPException(status_code=404, detail="Отчёт не найден")
    return r


def _out(r: PdfReport) -> dict:
    return {
        "id": r.id,
        "chart_id": r.chart_id,
        "tier": r.tier,
        "tier_name": TIER_NAMES.get(r.tier, r.tier),
        "status": r.status,
        "progress": r.progress,
        "step": r.step,
        "error": FAIL_TEXT if r.status == "failed" else None,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "ready_at": r.ready_at.isoformat() if r.ready_at else None,
        "expires_at": r.expires_at.isoformat() if r.expires_at else None,
        "new": r.status == "ready" and r.seen_at is None,
    }


@router.post("/chart/{chart_id}/pdf-reports", status_code=202)
@limiter.limit("10/minute")
async def start_report(
    request: Request,
    chart_id: str,
    body: PdfStart | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    chart = _own_chart(db, chart_id, user)
    report, queued = start(db, user, chart, body.wheel_png if body else None)
    return {**_out(report), "queued": queued}


@router.get("/chart/{chart_id}/pdf-reports")
async def list_reports(
    chart_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _own_chart(db, chart_id, user)
    rows = (
        db.query(PdfReport)
        .filter(PdfReport.chart_id == chart_id, PdfReport.user_id == user.id,
                PdfReport.status.in_(("ready", *ACTIVE)), PdfReport.expires_at > utcnow())
        .order_by(PdfReport.created_at.desc())
        .all()
    )
    return {"reports": [_out(r) for r in rows]}


@router.get("/pdf-reports/{report_id}")
async def report_status(
    report_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return _out(_own_report(db, report_id, user))


@router.get("/pdf-reports/{report_id}/file")
async def report_file(
    report_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    r = _own_report(db, report_id, user)
    if r.status != "ready" or not r.file_path or not os.path.exists(r.file_path):
        raise HTTPException(status_code=404, detail="Файл не найден — собери PDF заново")
    if r.seen_at is None:
        r.seen_at = utcnow()
        db.commit()
    chart = db.get(NatalChart, r.chart_id)
    name = (getattr(chart, "name", None) or "").strip()
    filename = f"Натальная карта — {name}.pdf" if name else "Натальная карта.pdf"
    return FileResponse(r.file_path, media_type="application/pdf", filename=filename)
