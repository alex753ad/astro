"""Client portal router (roadmap idea 10) — публичные read-only страницы клиента.

Endpoints:
  GET /api/v1/portal/{token}   — JSON: бренд + карта + домашние задания (публично)
  GET /portal-report/{token}   — PDF натальной карты под брендом (публично)
"""
from __future__ import annotations

import logging
import urllib.parse

from fastapi import APIRouter, Depends, HTTPException
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


@router.get("/portal-report/{token}")
async def portal_report(token: str, db: Session = Depends(get_db)):
    _, client, astrologer = _resolve(token, db)
    if not client.natal_chart_id:
        raise HTTPException(status_code=404, detail="Chart not calculated yet")
    chart = db.query(NatalChart).filter(NatalChart.id == client.natal_chart_id).first()
    if not chart:
        raise HTTPException(status_code=404, detail="Chart not found")

    brand = (astrologer.display_name if astrologer else None) or "Ваш астролог"
    try:
        from backend.natal_pdf import generate_pdf_bytes
        pdf_bytes = generate_pdf_bytes(chart, interpretation="", astrologer_name=brand)
    except Exception as e:
        logger.warning("Portal PDF generation failed: %s", e)
        raise HTTPException(status_code=503, detail="PDF временно недоступен")

    filename = f"natal_{chart.birth_date}.pdf"
    encoded = urllib.parse.quote(f"natal_{client.name}_{chart.birth_date}.pdf")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}; filename*=UTF-8''{encoded}"},
    )
