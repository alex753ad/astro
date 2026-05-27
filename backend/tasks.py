"""Celery tasks for heavy computations.

Tasks:
  task_calculate_transits  — transit calculation for up to 12 months (~8 sec)
  task_generate_pdf        — PDF report generation (~5-15 sec)
"""

from __future__ import annotations

import io
import logging
from datetime import date as date_type

from backend.celery_app import celery_app
from backend.database import SessionLocal
from backend.models import NatalChart

logger = logging.getLogger("astro.tasks")


def _get_chart(db, chart_id: str) -> NatalChart:
    chart = db.query(NatalChart).filter(NatalChart.id == chart_id).first()
    if not chart:
        raise ValueError(f"Chart not found: {chart_id}")
    return chart


# ═══════════════════════════════════════════════════════════
# TASK: Calculate transits
# ═══════════════════════════════════════════════════════════

@celery_app.task(bind=True, name="tasks.calculate_transits")
def task_calculate_transits(
    self,
    chart_id: str,
    from_date: str,
    to_date: str,
    planet_filter: str | None = None,
    max_orb: float | None = None,
) -> dict:
    """Calculate transits for up to 12 months.

    Returns serialized list of TransitEvent dicts.
    """
    from backend.transit.engine import calculate_transits
    from backend.cache import transit_cache

    self.update_state(state="STARTED", meta={"step": "loading_chart"})

    db = SessionLocal()
    try:
        chart = _get_chart(db, chart_id)

        cache_key = f"transit:{chart_id}:{from_date}:{to_date}:{planet_filter}:{max_orb}"
        cached = transit_cache.get(cache_key)
        if cached:
            logger.info("Transit cache hit in task: %s", cache_key[:40])
            return {"events": cached, "cached": True}

        self.update_state(state="STARTED", meta={"step": "calculating"})

        from_dt = date_type.fromisoformat(from_date)
        to_dt = date_type.fromisoformat(to_date)
        planet_list = [planet_filter] if planet_filter else None

        events = calculate_transits(
            natal_planets=chart.planets,
            from_date=from_dt,
            to_date=to_dt,
            orb_filter=max_orb,
            planet_filter=planet_list,
        )

        self.update_state(state="STARTED", meta={"step": "serializing"})

        events_data = [
            {
                "start_date": getattr(e, "start_date", None) or getattr(e, "date", ""),
                "peak_date":  getattr(e, "peak_date",  None) or getattr(e, "date", ""),
                "end_date":   getattr(e, "end_date",   None) or getattr(e, "date", ""),
                "transit_planet": e.transit_planet,
                "transit_sign":   getattr(e, "transit_sign", ""),
                "natal_planet":   e.natal_planet,
                "natal_sign":     getattr(e, "natal_sign", ""),
                "aspect_type":    e.aspect_type,
                "peak_orb":       getattr(e, "peak_orb", None) or getattr(e, "orb", 0.0),
                "exact_date":     getattr(e, "exact_date", None),
                "applying":       getattr(e, "applying", True),
            }
            for e in events
        ]

        transit_cache.set(cache_key, events_data, ttl=7 * 24 * 3600)

        return {"events": events_data, "cached": False}

    except Exception as exc:
        logger.exception("task_calculate_transits failed: %s", exc)
        raise
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════
# TASK: Generate PDF
# ═══════════════════════════════════════════════════════════

@celery_app.task(bind=True, name="tasks.generate_pdf")
def task_generate_pdf(self, chart_id: str) -> dict:
    """Generate a PDF natal chart report.

    Returns base64-encoded PDF bytes.
    """
    import base64

    self.update_state(state="STARTED", meta={"step": "loading_chart"})

    db = SessionLocal()
    try:
        chart = _get_chart(db, chart_id)
        self.update_state(state="STARTED", meta={"step": "rendering_pdf"})

        pdf_bytes = _render_pdf(chart)
        pdf_b64 = base64.b64encode(pdf_bytes).decode("utf-8")

        return {
            "chart_id": chart_id,
            "filename": f"natal_chart_{chart_id[:8]}.pdf",
            "pdf_base64": pdf_b64,
            "size_bytes": len(pdf_bytes),
        }

    except Exception as exc:
        logger.exception("task_generate_pdf failed: %s", exc)
        raise
    finally:
        db.close()


def _render_pdf(chart: NatalChart) -> bytes:
    """Render PDF using reportlab. Falls back to plain text if not installed."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.lib import colors
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        )

        buf = io.BytesIO()
        doc = SimpleDocTemplate(
            buf, pagesize=A4,
            leftMargin=2*cm, rightMargin=2*cm,
            topMargin=2*cm, bottomMargin=2*cm,
        )

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "Title", parent=styles["Title"],
            fontSize=20, textColor=colors.HexColor("#4A2C8C"),
            spaceAfter=12,
        )
        heading_style = ParagraphStyle(
            "Heading", parent=styles["Heading2"],
            fontSize=13, textColor=colors.HexColor("#6B46C1"),
            spaceBefore=14, spaceAfter=6,
        )
        body_style = styles["Normal"]

        elements = []

        # ── Заголовок ──
        elements.append(Paragraph("✦ Натальная карта", title_style))
        elements.append(Spacer(1, 0.3*cm))

        # ── Данные рождения ──
        birth_info = [
            ["Дата рождения", chart.birth_date or "—"],
            ["Время рождения", chart.birth_time or "Неизвестно"],
            ["Место рождения", chart.birth_place or "—"],
            ["Часовой пояс",   chart.timezone or "—"],
        ]
        t = Table(birth_info, colWidths=[5*cm, 11*cm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (0,-1), colors.HexColor("#F3F0FF")),
            ("TEXTCOLOR",  (0,0), (0,-1), colors.HexColor("#4A2C8C")),
            ("FONTNAME",   (0,0), (0,-1), "Helvetica-Bold"),
            ("FONTSIZE",   (0,0), (-1,-1), 10),
            ("ROWBACKGROUNDS", (0,0), (-1,-1), [colors.white, colors.HexColor("#FAF9FF")]),
            ("GRID",       (0,0), (-1,-1), 0.5, colors.HexColor("#D1C4E9")),
            ("PADDING",    (0,0), (-1,-1), 6),
        ]))
        elements.append(t)
        elements.append(Spacer(1, 0.5*cm))

        # ── Планеты ──
        elements.append(Paragraph("Позиции планет", heading_style))
        planet_data = [["Планета", "Знак", "Градус", "Дом", "R"]]
        for p in (chart.planets or []):
            planet_data.append([
                p.get("name", ""),
                p.get("sign", ""),
                f"{p.get('degree_in_sign', 0):.1f}°",
                str(p.get("house") or "—"),
                "℞" if p.get("retrograde") else "",
            ])
        pt = Table(planet_data, colWidths=[4*cm, 4*cm, 3*cm, 3*cm, 2*cm])
        pt.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#6B46C1")),
            ("TEXTCOLOR",  (0,0), (-1,0), colors.white),
            ("FONTNAME",   (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTSIZE",   (0,0), (-1,-1), 9),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#FAF9FF")]),
            ("GRID",       (0,0), (-1,-1), 0.5, colors.HexColor("#D1C4E9")),
            ("PADDING",    (0,0), (-1,-1), 5),
        ]))
        elements.append(pt)
        elements.append(Spacer(1, 0.5*cm))

        # ── Аспекты ──
        elements.append(Paragraph("Аспекты", heading_style))
        aspect_data = [["Планета 1", "Аспект", "Планета 2", "Орб"]]
        for a in (chart.aspects or [])[:20]:   # топ-20
            aspect_data.append([
                a.get("planet1", ""),
                a.get("aspect_type", ""),
                a.get("planet2", ""),
                f"{a.get('orb', 0):.2f}°",
            ])
        at = Table(aspect_data, colWidths=[4*cm, 4*cm, 4*cm, 4*cm])
        at.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#6B46C1")),
            ("TEXTCOLOR",  (0,0), (-1,0), colors.white),
            ("FONTNAME",   (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTSIZE",   (0,0), (-1,-1), 9),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#FAF9FF")]),
            ("GRID",       (0,0), (-1,-1), 0.5, colors.HexColor("#D1C4E9")),
            ("PADDING",    (0,0), (-1,-1), 5),
        ]))
        elements.append(at)

        # ── Футер ──
        elements.append(Spacer(1, 1*cm))
        elements.append(Paragraph(
            "Создано Astrea Timeline · Swiss Ephemeris · astro-navy-one.vercel.app",
            ParagraphStyle("footer", parent=body_style, fontSize=8,
                           textColor=colors.grey, alignment=1),
        ))

        doc.build(elements)
        return buf.getvalue()

    except ImportError:
        # Fallback: plain text "PDF" если reportlab не установлен
        logger.warning("reportlab not installed, generating plain text PDF")
        return _render_plain_text_pdf(chart)


def _render_plain_text_pdf(chart: NatalChart) -> bytes:
    """Minimal plain-text fallback (не настоящий PDF, но отдаёт байты)."""
    lines = [
        "НАТАЛЬНАЯ КАРТА",
        "=" * 40,
        f"Дата: {chart.birth_date}",
        f"Время: {chart.birth_time or 'Неизвестно'}",
        f"Место: {chart.birth_place}",
        "",
        "ПЛАНЕТЫ",
        "-" * 40,
    ]
    for p in (chart.planets or []):
        lines.append(
            f"{p.get('name',''):<14} {p.get('sign',''):<12} {p.get('degree_in_sign',0):.1f}°"
            + (" R" if p.get("retrograde") else "")
        )
    lines += ["", "Создано Astrea Timeline"]
    return "\n".join(lines).encode("utf-8")
