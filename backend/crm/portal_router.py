"""Client portal router (roadmap idea 10) — публичные read-only страницы клиента.

Endpoints:
  GET /api/v1/portal/{token}   — JSON: бренд + карта + домашние задания (публично)
  GET /portal-report/{token}   — PDF натальной карты под брендом (публично)
"""
from __future__ import annotations

import logging
import urllib.parse
from backend.time_utils import utcnow

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import (
    AstrologerProfile, ClientPortalAccess, ClientProfile, Consultation, NatalChart,
)

logger = logging.getLogger("astro.portal")

router = APIRouter(tags=["portal"])


def _resolve(token: str, db: Session):
    portal = db.query(ClientPortalAccess).filter(ClientPortalAccess.token == token).first()
    if not portal or not portal.enabled:
        raise HTTPException(status_code=404, detail="Portal not found")
    # Портал отдаёт ПДн клиента (дата и место рождения) без авторизации, поэтому
    # у ссылки должен быть срок. NULL = выдана до миграции 041, остаётся бессрочной.
    if portal.expires_at is not None and portal.expires_at < utcnow():
        raise HTTPException(status_code=404, detail="Portal not found")
    client = db.query(ClientProfile).filter(ClientProfile.id == portal.client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Portal not found")
    astrologer = db.query(AstrologerProfile).filter(AstrologerProfile.id == client.astrologer_id).first()
    return portal, client, astrologer


@router.get("/api/v1/portal/{token}")
async def portal_data(token: str, db: Session = Depends(get_db)):
    _, client, astrologer = _resolve(token, db)

    chart = None
    if client.natal_chart_id:
        c = db.query(NatalChart).filter(NatalChart.id == client.natal_chart_id).first()
        if c:
            chart = {
                "birth_date": c.birth_date,
                "birth_place": c.birth_place,
                "time_unknown": c.time_unknown,
                "planets": c.planets,
                "houses": c.houses,
                "aspects": c.aspects,
                "ascendant": c.ascendant,
                "midheaven": c.midheaven,
            }

    assignments = [
        {
            "date": str(cons.date or "")[:10],
            "topic": cons.topic,
            "assignment": cons.assignment,
        }
        for cons in (
            db.query(Consultation)
            .filter(Consultation.client_id == client.id)
            .filter(Consultation.assignment.isnot(None))
            .order_by(Consultation.date.desc())
            .all()
        )
        if (cons.assignment or "").strip()
    ]

    return {
        "astrologer_name": (astrologer.display_name if astrologer else None) or "Ваш астролог",
        "client_name": client.name,
        "has_report": client.natal_chart_id is not None,
        "chart": chart,
        "assignments": assignments,
    }


# methods=["GET", "HEAD"]: FastAPI, в отличие от Starlette, не добавляет HEAD
# к GET-маршрутам сам (fastapi/routing.py:892 против starlette/routing.py:229-234).
# Ссылку на этот PDF присылают в мессенджер, а краулер превью сначала делает
# HEAD — на 405 он останавливается. Подробности в CLAUDE.md.
@router.api_route("/portal-report/{token}", methods=["GET", "HEAD"])
async def portal_report(token: str, request: Request, db: Session = Depends(get_db)):
    _, client, astrologer = _resolve(token, db)
    if not client.natal_chart_id:
        raise HTTPException(status_code=404, detail="Chart not calculated yet")
    chart = db.query(NatalChart).filter(NatalChart.id == client.natal_chart_id).first()
    if not chart:
        raise HTTPException(status_code=404, detail="Chart not found")

    # Имя файла считается ЗДЕСЬ, после всех проверок 404, и это условие
    # работы, а не порядок ради красоты: в нём имя клиента и дата рождения,
    # то есть персональные данные. Поднимется выше проверок — HEAD с чужим
    # или протухшим токеном начнёт отдавать их в Content-Disposition, не
    # отдав ни байта PDF. Закреплено тестом (плохой токен → 404 и никакого
    # Content-Disposition).
    filename = f"natal_{chart.birth_date}.pdf"
    encoded = urllib.parse.quote(f"natal_{client.name}_{chart.birth_date}.pdf")
    disposition = f"attachment; filename={filename}; filename*=UTF-8''{encoded}"

    # ── Ранний выход по HEAD ────────────────────────────────────────────────
    # После проверок токена (иначе ручка стала бы оракулом существования
    # порталов) и до generate_pdf_bytes — ReportLab собирает PDF целиком,
    # синхронно, а тело всё равно будет отброшено на уровне ASGI.
    #
    # ⚠️ Расхождение с GET, принятое осознанно: обнаружить сбой генерации, не
    # выполнив её, HEAD не может, поэтому здесь он отвечает 200 там, где GET
    # ответил бы 503. Утечки нет — 503 не зависит от токена и одинаков для
    # всех. Content-Length намеренно не выставляется: настоящий размер без
    # генерации неизвестен, а неверный хуже отсутствующего.
    if request.method == "HEAD":
        return Response(
            media_type="application/pdf",
            headers={"Content-Disposition": disposition},
        )

    brand = (astrologer.display_name if astrologer else None) or "Ваш астролог"
    try:
        from backend.natal_pdf import generate_pdf_bytes
        pdf_bytes = generate_pdf_bytes(chart, interpretation="", astrologer_name=brand)
    except Exception as e:
        logger.warning("Portal PDF generation failed: %s", e)
        raise HTTPException(status_code=503, detail="PDF временно недоступен")

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": disposition},
    )
