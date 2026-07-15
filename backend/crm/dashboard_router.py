"""CRM dashboard router (roadmap idea 3 — транзитные алерты по базе).

GET /api/v1/crm/alerts?from=&to= → важные периоды по всем клиентам астролога.

Алерт = медленная планета в аспекте к личной точке натала, пик которого
попадает в окно [from, to] и укладывается в порог точности (peak_orb ≤ MAX_ORB).
Фильтр по типу аспекта не применяется: транзитный движок и так отдаёт только
реальные аспекты в пределах своего орба. Считается на лету (без кэша/таблицы).
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import AstrologerProfile, ClientBroadcastLog, ClientIntake, ClientProfile, Consultation, NatalChart, User
from backend.auth.dependencies import require_tier

logger = logging.getLogger("astro.crm")

router = APIRouter(prefix="/api/v1/crm", tags=["crm"])

_premium = Depends(require_tier("premium"))

SLOW_PLANETS = {"Jupiter", "Saturn", "Uranus", "Neptune", "Pluto"}
PERSONAL_POINTS = {"Sun", "Moon", "Mercury", "Venus", "Mars"}
MAX_ORB = 3.0  # «точный» транзит; поднимите, если нужно ловить шире


@router.get("/alerts")
async def get_alerts(
    from_date: date = Query(None, alias="from"),
    to_date: date = Query(None, alias="to"),
    user: User = _premium,
    db: Session = Depends(get_db),
):
    from backend.transit.engine import calculate_transits

    astrologer = db.query(AstrologerProfile).filter(
        AstrologerProfile.user_id == user.id
    ).first()
    if not astrologer:
        return []

    today = date.today()
    frm = from_date or today
    to = to_date or (today + timedelta(days=7))

    rows = (
        db.query(ClientProfile, NatalChart)
        .join(NatalChart, ClientProfile.natal_chart_id == NatalChart.id)
        .filter(ClientProfile.astrologer_id == astrologer.id)
        .all()
    )

    alerts = []
    for client, chart in rows:
        try:
            events = calculate_transits(
                natal_planets=chart.planets,
                from_date=frm,
                to_date=to,
            )
        except Exception as e:
            logger.warning("Alerts: transit calc failed for client %s: %s", client.id, e)
            continue

        for ev in events:
            if ev.transit_planet not in SLOW_PLANETS:
                continue
            if ev.natal_planet not in PERSONAL_POINTS:
                continue
            orb = getattr(ev, "peak_orb", None)
            if orb is not None and orb > MAX_ORB:
                continue
            alerts.append({
                "client_id": client.id,
                "name": client.name,
                "event": f"{ev.transit_planet} {ev.aspect_type} {ev.natal_planet}",
                "exact_date": str(getattr(ev, "peak_date", "") or ""),
                "orb": round(orb, 2) if orb is not None else None,
            })

    alerts.sort(key=lambda a: a["exact_date"])
    return alerts


# ── Monthly broadcast (021 / roadmap idea 5) ──

class BroadcastPreviewIn(BaseModel):
    client_id: int
    mode: str = "template"  # "template" | "ai"
    custom_text: Optional[str] = None  # авторский текст астролога в письмо


class BroadcastSendIn(BaseModel):
    client_ids: Optional[list[int]] = None
    mode: str = "template"  # "template" | "ai"
    custom_text: Optional[str] = None  # авторский текст астролога в письмо


class ProfilePatch(BaseModel):
    display_name: Optional[str] = None
    broadcast_auto: Optional[bool] = None


def _astrologer_or_404(user: User, db: Session) -> AstrologerProfile:
    astrologer = db.query(AstrologerProfile).filter(AstrologerProfile.user_id == user.id).first()
    if not astrologer:
        raise HTTPException(status_code=404, detail="Astrologer profile not found")
    return astrologer


def _month_transits(chart: NatalChart) -> list[dict]:
    from backend.transit.engine import calculate_transits
    today = date.today()
    events = calculate_transits(
        natal_planets=chart.planets, from_date=today, to_date=today + timedelta(days=30)
    )
    return [
        {
            "transit_planet": e.transit_planet,
            "natal_planet": e.natal_planet,
            "aspect_type": e.aspect_type,
            "peak_date": getattr(e, "peak_date", None),
            "peak_orb": getattr(e, "peak_orb", None),
        }
        for e in events
    ]


@router.post("/broadcast/preview")
async def broadcast_preview(
    payload: BroadcastPreviewIn,
    user: User = _premium,
    db: Session = Depends(get_db),
):
    import uuid
    from backend.email_service import build_client_broadcast, build_broadcast_ai_prompt, ru_month_label, PUBLIC_API_URL

    astrologer = _astrologer_or_404(user, db)
    client = db.query(ClientProfile).filter(
        ClientProfile.id == payload.client_id,
        ClientProfile.astrologer_id == astrologer.id,
    ).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    if not client.natal_chart_id:
        raise HTTPException(status_code=400, detail="Chart not calculated yet")
    chart = db.query(NatalChart).filter(NatalChart.id == client.natal_chart_id).first()
    if not chart:
        raise HTTPException(status_code=404, detail="Chart not found")

    brand = astrologer.display_name or "Ваш астролог"
    period_label = ru_month_label(date.today())
    transits = _month_transits(chart)

    if not client.unsubscribe_token:
        client.unsubscribe_token = uuid.uuid4().hex
        db.commit()
    unsub_url = f"{PUBLIC_API_URL}/api/v1/crm/unsubscribe/{client.unsubscribe_token}"

    ai_text = None
    if payload.mode == "ai":
        try:
            from backend.interpretation.base import InterpretationRequest
            from backend.interpretation.router import get_router
            profile = {
                "planets": chart.planets, "houses": chart.houses, "aspects": chart.aspects,
                "ascendant": chart.ascendant, "midheaven": chart.midheaven, "time_unknown": chart.time_unknown,
            }
            req = InterpretationRequest(
                natal_profile=profile, context="transit", tier=user.tier,
                custom_prompt=build_broadcast_ai_prompt(period_label, transits),
            )
            result = await get_router().generate(req)
            ai_text = (result.content or "").strip() or None
        except Exception as e:
            logger.warning("Preview AI generation failed: %s", e)

    subject, html = build_client_broadcast(
        brand, period_label, transits, unsubscribe_url=unsub_url, ai_text=ai_text,
        custom_text=payload.custom_text,
    )
    return {"subject": subject, "html": html, "to": client.email, "ai": bool(ai_text)}


@router.post("/broadcast/send")
async def broadcast_send(
    payload: BroadcastSendIn,
    user: User = _premium,
    db: Session = Depends(get_db),
):
    from backend.tasks import send_client_broadcast_task

    astrologer = _astrologer_or_404(user, db)
    recipients = (
        db.query(ClientProfile.id)
        .filter(ClientProfile.astrologer_id == astrologer.id)
        .filter(ClientProfile.email.isnot(None))
        .filter(ClientProfile.natal_chart_id.isnot(None))
        .filter(ClientProfile.broadcast_opt_out == False)  # noqa: E712
    )
    if payload.client_ids:
        recipients = recipients.filter(ClientProfile.id.in_(payload.client_ids))
    count = recipients.count()

    mode = "ai" if payload.mode == "ai" else "template"
    send_client_broadcast_task.delay(astrologer.id, payload.client_ids, None, mode,
                                     custom_text=payload.custom_text)
    return {"queued": True, "recipients": count, "mode": mode}


# ── Astrologer brand/profile (022) ──

def _get_or_create_astrologer(user: User, db: Session) -> AstrologerProfile:
    astrologer = db.query(AstrologerProfile).filter(AstrologerProfile.user_id == user.id).first()
    if not astrologer:
        astrologer = AstrologerProfile(user_id=user.id, display_name=user.name or user.email)
        db.add(astrologer)
        db.commit()
        db.refresh(astrologer)
    return astrologer


@router.get("/profile")
async def get_profile(user: User = _premium, db: Session = Depends(get_db)):
    astrologer = _get_or_create_astrologer(user, db)
    return {"display_name": astrologer.display_name, "broadcast_auto": astrologer.broadcast_auto}


@router.patch("/profile")
async def patch_profile(payload: ProfilePatch, user: User = _premium, db: Session = Depends(get_db)):
    astrologer = _get_or_create_astrologer(user, db)
    if payload.display_name is not None:
        astrologer.display_name = payload.display_name.strip() or None
    if payload.broadcast_auto is not None:
        astrologer.broadcast_auto = payload.broadcast_auto
    db.commit()
    db.refresh(astrologer)
    return {"display_name": astrologer.display_name, "broadcast_auto": astrologer.broadcast_auto}


# ── Public unsubscribe (022, без авторизации) ──

@router.get("/unsubscribe/{token}", response_class=HTMLResponse)
async def unsubscribe(token: str, db: Session = Depends(get_db)):
    client = db.query(ClientProfile).filter(ClientProfile.unsubscribe_token == token).first()
    if client and not client.broadcast_opt_out:
        client.broadcast_opt_out = True
        db.commit()
    ok = client is not None
    msg = "Вы отписались от рассылки." if ok else "Ссылка недействительна."
    return HTMLResponse(
        f"""<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/><title>Отписка</title></head>
<body style="margin:0;background:#0e0c1a;font-family:'Segoe UI',Arial,sans-serif;color:#e8e0f4;">
  <div style="max-width:480px;margin:80px auto;padding:40px;background:#1a1030;border-radius:16px;text-align:center;">
    <div style="font-size:22px;font-weight:700;color:#c9a8ff;margin-bottom:12px;">{msg}</div>
    <div style="font-size:14px;color:#a090c0;">Больше писем этой рассылки вы не получите.</div>
  </div>
</body></html>"""
    )


@router.get("/broadcast/history")
async def broadcast_history(
    user: User = _premium,
    db: Session = Depends(get_db),
):
    astrologer = _astrologer_or_404(user, db)
    rows = (
        db.query(ClientBroadcastLog, ClientProfile.name)
        .join(ClientProfile, ClientBroadcastLog.client_id == ClientProfile.id)
        .filter(ClientBroadcastLog.astrologer_id == astrologer.id)
        .order_by(ClientBroadcastLog.created_at.desc())
        .limit(100)
        .all()
    )
    return [
        {
            "client_id": log.client_id,
            "name": name,
            "period_ym": log.period_ym,
            "status": log.status,
            "sent_at": str(log.sent_at or ""),
        }
        for log, name in rows
    ]


# ── Client intake forms (023 / roadmap idea 6) ──

import os as _os
import secrets as _secrets
from datetime import datetime as _datetime

_INTAKE_APP_URL = _os.getenv("APP_URL", "https://astreatime.ru")


class IntakeSubmitIn(BaseModel):
    name: str
    birth_date: str
    birth_time: Optional[str] = None
    birth_place: str
    email: Optional[str] = None
    question: Optional[str] = None


def _intake_or_404(intake_id: int, astrologer: AstrologerProfile, db: Session) -> ClientIntake:
    intake = db.query(ClientIntake).filter(
        ClientIntake.id == intake_id,
        ClientIntake.astrologer_id == astrologer.id,
    ).first()
    if not intake:
        raise HTTPException(status_code=404, detail="Intake not found")
    return intake


@router.post("/intake/create")
async def intake_create(user: User = _premium, db: Session = Depends(get_db)):
    astrologer = _get_or_create_astrologer(user, db)
    intake = ClientIntake(astrologer_id=astrologer.id, token=_secrets.token_urlsafe(24), status="pending")
    db.add(intake)
    db.commit()
    db.refresh(intake)
    return {"id": intake.id, "token": intake.token, "url": f"{_INTAKE_APP_URL}/intake/{intake.token}"}


@router.get("/intake/list")
async def intake_list(user: User = _premium, db: Session = Depends(get_db)):
    astrologer = _get_or_create_astrologer(user, db)
    rows = (
        db.query(ClientIntake)
        .filter(ClientIntake.astrologer_id == astrologer.id)
        .filter(ClientIntake.status != "archived")
        .order_by(ClientIntake.created_at.desc())
        .limit(100)
        .all()
    )
    return [
        {
            "id": r.id,
            "token": r.token,
            "status": r.status,
            "url": f"{_INTAKE_APP_URL}/intake/{r.token}",
            "submitted_data": r.submitted_data,
            "submitted_at": str(r.submitted_at or ""),
            "client_id": r.client_id,
        }
        for r in rows
    ]


@router.post("/intake/{intake_id}/convert")
async def intake_convert(intake_id: int, user: User = _premium, db: Session = Depends(get_db)):
    from backend.crm.router import create_client, ClientCreate

    astrologer = _get_or_create_astrologer(user, db)
    intake = _intake_or_404(intake_id, astrologer, db)
    if intake.status == "converted":
        raise HTTPException(status_code=409, detail="Already converted")
    data = intake.submitted_data or {}
    if not data.get("name") or not data.get("birth_date") or not data.get("birth_place"):
        raise HTTPException(status_code=400, detail="Intake has no submitted data yet")

    question = (data.get("question") or "").strip()
    notes = f"Вопрос клиента: {question}" if question else None
    payload = ClientCreate(
        name=data["name"],
        birth_date=data["birth_date"],
        birth_time=data.get("birth_time") or None,
        birth_place=data["birth_place"],
        email=data.get("email") or None,
        notes=notes,
    )
    client = await create_client(payload=payload, user=user, db=db)

    intake.status = "converted"
    intake.client_id = client.id
    db.commit()
    return {"ok": True, "client_id": client.id}


@router.delete("/intake/{intake_id}", status_code=204)
async def intake_delete(intake_id: int, user: User = _premium, db: Session = Depends(get_db)):
    astrologer = _get_or_create_astrologer(user, db)
    intake = _intake_or_404(intake_id, astrologer, db)
    db.delete(intake)
    db.commit()


# ── Public intake (без авторизации) ──

@router.get("/intake/{token}")
async def intake_public_get(token: str, db: Session = Depends(get_db)):
    intake = db.query(ClientIntake).filter(ClientIntake.token == token).first()
    if not intake:
        raise HTTPException(status_code=404, detail="Not found")
    astrologer = db.query(AstrologerProfile).filter(AstrologerProfile.id == intake.astrologer_id).first()
    return {
        "astrologer_name": (astrologer.display_name if astrologer else None) or "Ваш астролог",
        "status": intake.status,
        "submitted": intake.submitted_at is not None,
    }


@router.post("/intake/{token}/submit")
async def intake_public_submit(token: str, payload: IntakeSubmitIn, db: Session = Depends(get_db)):
    intake = db.query(ClientIntake).filter(ClientIntake.token == token).first()
    if not intake:
        raise HTTPException(status_code=404, detail="Not found")
    if intake.status != "pending":
        raise HTTPException(status_code=409, detail="Эта анкета уже обработана")

    intake.submitted_data = {
        "name": payload.name.strip(),
        "birth_date": payload.birth_date,
        "birth_time": (payload.birth_time or None),
        "birth_place": payload.birth_place.strip(),
        "email": (payload.email or None),
        "question": (payload.question or None),
    }
    intake.submitted_at = _datetime.utcnow()
    db.commit()
    return {"ok": True}


# ── Practice analytics (09 / 15 / 16) ──

_SIGN_RU = {
    "Aries": "Овен", "Taurus": "Телец", "Gemini": "Близнецы", "Cancer": "Рак",
    "Leo": "Лев", "Virgo": "Дева", "Libra": "Весы", "Scorpio": "Скорпион",
    "Sagittarius": "Стрелец", "Capricorn": "Козерог", "Aquarius": "Водолей", "Pisces": "Рыбы",
}
_ELEMENTS = {
    "огонь": {"Aries", "Leo", "Sagittarius"},
    "земля": {"Taurus", "Virgo", "Capricorn"},
    "воздух": {"Gemini", "Libra", "Aquarius"},
    "вода": {"Cancer", "Scorpio", "Pisces"},
}


def _planet_sign(planets, name: str):
    for p in (planets or []):
        if p.get("name") == name:
            return p.get("sign")
    return None


def _element_of(sign: str):
    for el, signs in _ELEMENTS.items():
        if sign in signs:
            return el
    return None


@router.get("/stats")
async def crm_stats(
    from_date: date = Query(None, alias="from"),
    to_date: date = Query(None, alias="to"),
    user: User = _premium,
    db: Session = Depends(get_db),
):
    """№9 — доход и статистика по проведённым консультациям (status=done)."""
    astrologer = _get_or_create_astrologer(user, db)
    q = (
        db.query(Consultation)
        .join(ClientProfile, Consultation.client_id == ClientProfile.id)
        .filter(ClientProfile.astrologer_id == astrologer.id)
        .filter(Consultation.status == "done")
    )
    if from_date:
        q = q.filter(Consultation.date >= from_date)
    if to_date:
        q = q.filter(Consultation.date < to_date + timedelta(days=1))
    rows = q.all()

    revenue = sum((c.price or 0) for c in rows)
    count = len(rows)
    by_topic = {}
    for c in rows:
        t = c.topic or "—"
        e = by_topic.setdefault(t, {"count": 0, "revenue": 0})
        e["count"] += 1
        e["revenue"] += (c.price or 0)

    return {
        "revenue": revenue,
        "count": count,
        "avg_check": round(revenue / count) if count else 0,
        "by_topic": by_topic,
    }


@router.get("/history")
async def crm_history(
    months: int = Query(6, ge=1, le=24),
    user: User = _premium,
    db: Session = Depends(get_db),
):
    """Помесячная разбивка консультаций и дохода за последние N месяцев."""
    from datetime import datetime as _dt

    astrologer = _get_or_create_astrologer(user, db)
    now = _dt.utcnow()

    result = []
    for i in range(months - 1, -1, -1):
        mo = now.month - i
        yr = now.year
        while mo < 1:
            mo += 12; yr -= 1
        start = _dt(yr, mo, 1)
        end = _dt(yr + 1, 1, 1) if mo == 12 else _dt(yr, mo + 1, 1)

        rows = (
            db.query(Consultation)
            .join(ClientProfile, Consultation.client_id == ClientProfile.id)
            .filter(ClientProfile.astrologer_id == astrologer.id)
            .filter(Consultation.status == "done")
            .filter(Consultation.date >= start)
            .filter(Consultation.date < end)
            .all()
        )
        result.append({
            "month": f"{yr:04d}-{mo:02d}",
            "consultations": len(rows),
            "revenue": sum((c.price or 0) for c in rows),
        })

    return result


@router.get("/insights")
async def crm_insights(user: User = _premium, db: Session = Depends(get_db)):
    """№15 — инсайты по базе: знаки светил + частые темы."""
    astrologer = _get_or_create_astrologer(user, db)
    charts = (
        db.query(NatalChart.planets)
        .join(ClientProfile, ClientProfile.natal_chart_id == NatalChart.id)
        .filter(ClientProfile.astrologer_id == astrologer.id)
        .all()
    )
    sun_signs, moon_signs, moon_elements = {}, {}, {}
    for (planets,) in charts:
        s = _planet_sign(planets, "Sun")
        m = _planet_sign(planets, "Moon")
        if s:
            sun_signs[_SIGN_RU.get(s, s)] = sun_signs.get(_SIGN_RU.get(s, s), 0) + 1
        if m:
            moon_signs[_SIGN_RU.get(m, m)] = moon_signs.get(_SIGN_RU.get(m, m), 0) + 1
            el = _element_of(m)
            if el:
                moon_elements[el] = moon_elements.get(el, 0) + 1

    topics = (
        db.query(Consultation.topic, func.count(Consultation.id))
        .join(ClientProfile, Consultation.client_id == ClientProfile.id)
        .filter(ClientProfile.astrologer_id == astrologer.id)
        .filter(Consultation.topic.isnot(None))
        .group_by(Consultation.topic)
        .order_by(func.count(Consultation.id).desc())
        .limit(5)
        .all()
    )

    return {
        "clients_with_chart": len(charts),
        "sun_signs": sun_signs,
        "moon_signs": moon_signs,
        "moon_elements": moon_elements,
        "top_topics": [[t, n] for t, n in topics],
    }


@router.get("/reactivation")
async def crm_reactivation(
    months: int = Query(6),
    user: User = _premium,
    db: Session = Depends(get_db),
):
    """№16 — спящие клиенты (>N месяцев без консультаций) + повод (текущий транзит)."""
    from backend.transit.engine import calculate_transits

    astrologer = _get_or_create_astrologer(user, db)
    today = date.today()
    cutoff = today - timedelta(days=months * 30)

    # последняя дата консультации по каждому клиенту
    last_dates = dict(
        db.query(Consultation.client_id, func.max(Consultation.date))
        .join(ClientProfile, Consultation.client_id == ClientProfile.id)
        .filter(ClientProfile.astrologer_id == astrologer.id)
        .group_by(Consultation.client_id)
        .all()
    )

    clients = (
        db.query(ClientProfile, NatalChart)
        .outerjoin(NatalChart, ClientProfile.natal_chart_id == NatalChart.id)
        .filter(ClientProfile.astrologer_id == astrologer.id)
        .filter(ClientProfile.status != "archived")
        .all()
    )

    result = []
    for client, chart in clients:
        last = last_dates.get(client.id)
        last_d = last.date() if hasattr(last, "date") else last
        if last_d is not None and last_d >= cutoff:
            continue  # активный — не спящий

        reason = None
        if chart:
            try:
                events = calculate_transits(
                    natal_planets=chart.planets, from_date=today, to_date=today + timedelta(days=21)
                )
                for e in events:
                    if e.transit_planet in SLOW_PLANETS and e.natal_planet in PERSONAL_POINTS:
                        orb = getattr(e, "peak_orb", None)
                        if orb is None or orb <= MAX_ORB:
                            reason = f"{e.transit_planet} {e.aspect_type} {e.natal_planet}"
                            break
            except Exception as ex:
                logger.warning("Reactivation transit calc failed for %s: %s", client.id, ex)

        result.append({
            "client_id": client.id,
            "name": client.name,
            "last_consultation": str(last_d or ""),
            "reason": reason,
        })

    # сначала те, у кого есть повод (активный транзит)
    result.sort(key=lambda r: (r["reason"] is None, r["last_consultation"]))
    return result


# ── Group forecast (18) ──

class GroupForecastIn(BaseModel):
    client_ids: list[int]
    planet: Optional[str] = None   # фильтр по транзитной планете, напр. "Saturn"
    days: int = 30


@router.post("/group-forecast")
async def group_forecast(
    payload: GroupForecastIn,
    user: User = _premium,
    db: Session = Depends(get_db),
):
    """№18 — по выбранным клиентам: у кого значимый транзит в ближайший период."""
    from backend.transit.engine import calculate_transits

    astrologer = _get_or_create_astrologer(user, db)
    if not payload.client_ids:
        return []

    today = date.today()
    to = today + timedelta(days=max(1, min(payload.days, 90)))

    rows = (
        db.query(ClientProfile, NatalChart)
        .join(NatalChart, ClientProfile.natal_chart_id == NatalChart.id)
        .filter(ClientProfile.astrologer_id == astrologer.id)
        .filter(ClientProfile.id.in_(payload.client_ids))
        .all()
    )

    result = []
    for client, chart in rows:
        try:
            events = calculate_transits(natal_planets=chart.planets, from_date=today, to_date=to)
        except Exception as e:
            logger.warning("Group forecast transit calc failed for %s: %s", client.id, e)
            continue
        matches = []
        for e in events:
            if e.transit_planet not in SLOW_PLANETS:
                continue
            if e.natal_planet not in PERSONAL_POINTS:
                continue
            if payload.planet and e.transit_planet != payload.planet:
                continue
            orb = getattr(e, "peak_orb", None)
            if orb is not None and orb > MAX_ORB:
                continue
            matches.append({
                "event": f"{e.transit_planet} {e.aspect_type} {e.natal_planet}",
                "date": str(getattr(e, "peak_date", "") or "")[:10],
                "orb": round(orb, 2) if orb is not None else None,
            })
        if matches:
            matches.sort(key=lambda m: m["date"])
            result.append({"client_id": client.id, "name": client.name, "events": matches})

    result.sort(key=lambda r: r["events"][0]["date"])
    return result
