"""Celery tasks for heavy computations."""

from __future__ import annotations

import io
import logging
from backend.time_utils import utcnow

from backend.celery_app import celery_app
from backend.database import SessionLocal
from backend.models import NatalChart
from backend.chart_utils import get_primary_chart as _get_primary_chart  # noqa: F401 — реэкспорт для backend.pilot.cron и др.

logger = logging.getLogger("astro.tasks")


# ═══════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════

def _get_chart(db, chart_id: str) -> NatalChart:
    chart = db.query(NatalChart).filter(NatalChart.id == chart_id).first()
    if not chart:
        raise ValueError(f"Chart not found: {chart_id}")
    return chart


# ═══════════════════════════════════════════════════════════
# RETENTION EMAIL CHAIN
# ═══════════════════════════════════════════════════════════

@celery_app.task(name="tasks.send_retention_day2")
def send_retention_day2_task(user_id: int) -> None:
    from datetime import date as date_type, timedelta
    from backend.models import User
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return
        chart = _get_primary_chart(db, user)
        if not chart:
            return
        from backend.transit.engine import calculate_transits
        today = date_type.today()
        events = calculate_transits(natal_planets=chart.planets, from_date=today, to_date=today + timedelta(days=7))
        if not events:
            return
        # pick best positive transit
        POSITIVE = {"Venus", "Jupiter", "Sun"}
        POSITIVE_ASP = {"trine", "sextile", "conjunction"}
        event = next((e for e in events if getattr(e, "transit_planet", "") in POSITIVE and getattr(e, "aspect_type", "") in POSITIVE_ASP), events[0])
        from backend.ephemeris.ru_names import PLANET_RU, ASPECT_RU as ASP_RU
        tp = getattr(event, "transit_planet", "")
        np_ = getattr(event, "natal_planet", "")
        at = getattr(event, "aspect_type", "")
        text = (f"Сегодня <strong>{PLANET_RU.get(tp, tp)}</strong> образует "
                f"{ASP_RU.get(at, at)} с вашим натальным <strong>{PLANET_RU.get(np_, np_)}</strong>.")
        import asyncio
        from backend.email_service import send_retention_day2
        asyncio.run(send_retention_day2(user.email, text))
    except Exception as e:
        logger.warning("send_retention_day2_task failed user=%s: %s", user_id, e)
    finally:
        db.close()


@celery_app.task(name="tasks.send_retention_day7")
def send_retention_day7_task(user_id: int) -> None:
    from datetime import date as date_type, timedelta
    from backend.models import User
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user or user.tier != "free":
            return
        chart = _get_primary_chart(db, user)
        if not chart:
            return
        from backend.transit.engine import calculate_transits
        today = date_type.today()
        events = calculate_transits(natal_planets=chart.planets, from_date=today, to_date=today + timedelta(days=30))
        import asyncio
        from backend.email_service import send_retention_day7
        asyncio.run(send_retention_day7(user.email, max(0, len(events) - 1)))
    except Exception as e:
        logger.warning("send_retention_day7_task failed user=%s: %s", user_id, e)
    finally:
        db.close()


@celery_app.task(name="tasks.send_retention_day14")
def send_retention_day14_task(user_id: int) -> None:
    """Напоминание о тарифах для free-пользователей на 14-й день — без
    скидки и без купона (решение владельца, 19.08.2026)."""
    from backend.models import User
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user or user.tier != "free":
            return
        import asyncio
        from backend.email_service import send_retention_day14
        asyncio.run(
            send_retention_day14(user.email)
        )
    except Exception as e:
        logger.warning("send_retention_day14_task failed user=%s: %s", user_id, e)
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════
# LITE EMAIL CHAIN
# ═══════════════════════════════════════════════════════════

@celery_app.task(name="tasks.send_lite_welcome_task")
def send_lite_welcome_task(user_id: int) -> None:
    from backend.models import User
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return
        import asyncio
        from backend.email_service import send_lite_welcome
        asyncio.run(
            send_lite_welcome(user.email, name=user.name)
        )
    except Exception as e:
        logger.warning("send_lite_welcome_task failed user=%s: %s", user_id, e)
    finally:
        db.close()


@celery_app.task(name="tasks.send_lite_day14_task")
def send_lite_day14_task(user_id: int) -> None:
    from backend.models import User
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user or user.tier not in ("lite",):
            return
        import asyncio
        from backend.email_service import send_lite_day14
        asyncio.run(
            send_lite_day14(user.email, name=user.name)
        )
    except Exception as e:
        logger.warning("send_lite_day14_task failed user=%s: %s", user_id, e)
    finally:
        db.close()


@celery_app.task(name="tasks.schedule_lite_emails")
def schedule_lite_emails(user_id: int) -> None:
    """Запускается при апгрейде на Lite."""
    send_lite_welcome_task.apply_async(args=[user_id], countdown=60)
    send_lite_day14_task.apply_async(args=[user_id], countdown=14 * 24 * 3600)


# ═══════════════════════════════════════════════════════════
# PRO EMAIL CHAIN
# ═══════════════════════════════════════════════════════════

@celery_app.task(name="tasks.send_pro_welcome_task")
def send_pro_welcome_task(user_id: int) -> None:
    from backend.models import User
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return
        import asyncio
        from backend.email_service import send_pro_welcome
        asyncio.run(
            send_pro_welcome(user.email, name=user.name)
        )
    except Exception as e:
        logger.warning("send_pro_welcome_task failed user=%s: %s", user_id, e)
    finally:
        db.close()


@celery_app.task(name="tasks.send_pro_day30_task")
def send_pro_day30_task(user_id: int) -> None:
    from backend.models import User
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user or user.tier not in ("pro",):
            return
        import asyncio
        from backend.email_service import send_pro_day30
        asyncio.run(
            send_pro_day30(user.email, name=user.name)
        )
    except Exception as e:
        logger.warning("send_pro_day30_task failed user=%s: %s", user_id, e)
    finally:
        db.close()


@celery_app.task(name="tasks.schedule_pro_emails")
def schedule_pro_emails(user_id: int) -> None:
    """Запускается при апгрейде на Pro."""
    send_pro_welcome_task.apply_async(args=[user_id], countdown=60)
    send_pro_day30_task.apply_async(args=[user_id], countdown=30 * 24 * 3600)


# ═══════════════════════════════════════════════════════════
# PREMIUM EMAIL CHAIN
# ═══════════════════════════════════════════════════════════

@celery_app.task(name="tasks.send_premium_welcome_task")
def send_premium_welcome_task(user_id: int) -> None:
    from backend.models import User
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return
        import asyncio
        from backend.email_service import send_premium_welcome
        asyncio.run(
            send_premium_welcome(user.email, name=user.name)
        )
    except Exception as e:
        logger.warning("send_premium_welcome_task failed user=%s: %s", user_id, e)
    finally:
        db.close()


@celery_app.task(name="tasks.schedule_premium_emails")
def schedule_premium_emails(user_id: int) -> None:
    """Запускается при апгрейде на Premium."""
    send_premium_welcome_task.apply_async(args=[user_id], countdown=60)


@celery_app.task(name="tasks.schedule_retention_emails")
def schedule_retention_emails(user_id: int) -> None:
    """Запускает цепочку retention-писем после первой карты пользователя."""
    send_retention_day2_task.apply_async(args=[user_id], countdown=48 * 3600)
    send_retention_day7_task.apply_async(args=[user_id], countdown=7 * 24 * 3600)
    send_retention_day14_task.apply_async(args=[user_id], countdown=14 * 24 * 3600)


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


# ═══════════════════════════════════════════════════════════
# LUNAR RETURN CHECK (задача 2)
# ═══════════════════════════════════════════════════════════

@celery_app.task(name="tasks.check_lunar_returns")
def check_lunar_returns() -> dict:
    """Daily Celery task: send email when Moon returns to user's natal sign.

    Should be triggered via Railway Cron POST /api/v1/internal/lunar-returns (09:00 МСК).
    """
    import asyncio
    from datetime import date as date_type
    from backend.models import User, NatalChart
    from backend.transit.engine import get_next_lunar_return
    from backend.email_service import send_lunar_return_email

    db = SessionLocal()
    sent = 0
    today = date_type.today()

    try:
        users = db.query(User).filter(User.is_active == True).all()
        for user in users:
            chart = _get_primary_chart(db, user)
            if not chart or not chart.planets:
                continue
            try:
                natal_data = {"planets": chart.planets}
                lunar_date = get_next_lunar_return(natal_data, today)
                if lunar_date == today:
                    asyncio.run(
                        send_lunar_return_email(user, today)
                    )
                    sent += 1
            except Exception as e:
                logger.warning("Lunar return check failed user=%s: %s", user.id, e)
    finally:
        db.close()

    logger.info("check_lunar_returns: sent=%d", sent)
    return {"sent": sent, "date": str(today)}


@celery_app.task(name="tasks.send_weekly_digest_task")
def send_weekly_digest_task() -> dict:
    """Daily Celery Beat task: send weekly digest to users whose digest_day == today."""
    import asyncio
    from datetime import date as date_type
    from backend.models import User
    from backend.email_service import send_weekly_digest

    db = SessionLocal()
    sent = 0
    today_weekday = date_type.today().weekday()

    try:
        users = db.query(User).filter(
            User.tier.in_(["pro", "premium"]),
            User.digest_day_of_week == today_weekday,
            User.is_active == True,
        ).all()
        for user in users:
            try:
                ok = asyncio.run(
                    send_weekly_digest(user, db)
                )
                if ok:
                    sent += 1
            except Exception as e:
                logger.warning("Weekly digest failed user=%s: %s", user.id, e)
    finally:
        db.close()

    logger.info("send_weekly_digest_task: sent=%d weekday=%d", sent, today_weekday)
    return {"sent": sent, "weekday": today_weekday}


# ═══════════════════════════════════════════════════════════
# CLIENT BROADCAST (021 / roadmap idea 5, 022 auto+unsub+ai)
# ═══════════════════════════════════════════════════════════

def _ensure_unsub_token(client, db) -> str:
    if not client.unsubscribe_token:
        import uuid
        client.unsubscribe_token = uuid.uuid4().hex
        db.commit()
    return client.unsubscribe_token


def _unsub_url(token: str) -> str:
    from backend.email_service import PUBLIC_API_URL
    return f"{PUBLIC_API_URL}/api/v1/crm/unsubscribe/{token}"


async def _gen_broadcast_ai(profile: dict, tier: str, period_label: str, transits: list[dict]) -> str | None:
    """AI-текст для гибридного письма. None → откат на шаблон."""
    try:
        from backend.interpretation.base import InterpretationRequest
        from backend.interpretation.router import get_router
        from backend.email_service import build_broadcast_ai_prompt
        req = InterpretationRequest(
            natal_profile=profile,
            context="transit",
            tier=tier or "premium",
            custom_prompt=build_broadcast_ai_prompt(period_label, transits),
        )
        result = await get_router().generate(req)
        return (result.content or "").strip() or None
    except Exception as e:
        logger.warning("Broadcast AI generation failed: %s", e)
        return None


@celery_app.task(name="tasks.send_client_broadcast")
def send_client_broadcast_task(astrologer_id: int, client_ids=None, period_ym: str | None = None,
                               mode: str = "template", custom_text: str | None = None) -> dict:
    """Ежемесячная брендовая рассылка прогноза клиентам астролога.

    mode="ai" → AI-текст на каждого клиента (гибрид, платно); иначе шаблон.
    Пропускает отписавшихся и уже отправленных в этом period_ym.
    """
    import asyncio
    from datetime import date, timedelta

    from backend.models import AstrologerProfile, ClientProfile, ClientBroadcastLog, User
    from backend.transit.engine import calculate_transits
    from backend.email_service import send_client_broadcast, ru_month_label

    db = SessionLocal()
    sent, failed = 0, 0
    try:
        astrologer = db.query(AstrologerProfile).filter(
            AstrologerProfile.id == astrologer_id
        ).first()
        if not astrologer:
            return {"sent": 0, "failed": 0, "error": "astrologer not found"}

        brand = astrologer.display_name or "Ваш астролог"
        owner = db.query(User).filter(User.id == astrologer.user_id).first()
        tier = owner.tier if owner else "premium"

        today = date.today()
        ym = period_ym or today.strftime("%Y-%m")
        period_label = ru_month_label(today)

        q = (
            db.query(ClientProfile, NatalChart)
            .join(NatalChart, ClientProfile.natal_chart_id == NatalChart.id)
            .filter(ClientProfile.astrologer_id == astrologer_id)
            .filter(ClientProfile.email.isnot(None))
            .filter(ClientProfile.broadcast_opt_out == False)  # noqa: E712
        )
        if client_ids:
            q = q.filter(ClientProfile.id.in_(client_ids))
        rows = q.all()

        # Логи прошлой отправки за период — одним запросом на всю рассылку,
        # а не по одному SELECT на клиента: на базе в сотни клиентов цикл ниже
        # раньше давал сотни лишних обращений к БД на каждый прогон рассылки.
        logs_by_client = {
            log.client_id: log
            for log in db.query(ClientBroadcastLog).filter(
                ClientBroadcastLog.astrologer_id == astrologer_id,
                ClientBroadcastLog.period_ym == ym,
                ClientBroadcastLog.client_id.in_([c.id for c, _ in rows]),
            )
        } if rows else {}

        for client, chart in rows:
            email = (client.email or "").strip()
            if not email:
                continue

            log = logs_by_client.get(client.id)
            if log and log.status == "success":
                continue

            try:
                events = calculate_transits(
                    natal_planets=chart.planets,
                    from_date=today,
                    to_date=today + timedelta(days=30),
                )
                transits = [
                    {
                        "transit_planet": e.transit_planet,
                        "natal_planet": e.natal_planet,
                        "aspect_type": e.aspect_type,
                        "peak_date": getattr(e, "peak_date", None),
                        "peak_orb": getattr(e, "peak_orb", None),
                    }
                    for e in events
                ]
                profile = {
                    "planets": chart.planets, "houses": chart.houses, "aspects": chart.aspects,
                    "ascendant": chart.ascendant, "midheaven": chart.midheaven,
                    "time_unknown": chart.time_unknown,
                }
                token = _ensure_unsub_token(client, db)

                ai_text = None
                if mode == "ai":
                    ai_text = asyncio.run(
                        _gen_broadcast_ai(profile, tier, period_label, transits)
                    )

                ok = asyncio.run(
                    send_client_broadcast(
                        email, brand, period_label, transits,
                        unsubscribe_url=_unsub_url(token), ai_text=ai_text,
                        custom_text=custom_text,
                    )
                )
            except Exception as e:
                logger.warning("Broadcast to client %s failed: %s", client.id, e)
                ok = False

            if log:
                log.status = "success" if ok else "error"
                log.sent_at = utcnow() if ok else None
            else:
                db.add(ClientBroadcastLog(
                    astrologer_id=astrologer_id,
                    client_id=client.id,
                    period_ym=ym,
                    status="success" if ok else "error",
                    sent_at=utcnow() if ok else None,
                ))
            db.commit()
            sent += 1 if ok else 0
            failed += 0 if ok else 1
    finally:
        db.close()

    logger.info("send_client_broadcast_task: astro=%s mode=%s sent=%d failed=%d",
                astrologer_id, mode, sent, failed)
    return {"sent": sent, "failed": failed}


@celery_app.task(name="tasks.send_broadcast_auto")
def send_broadcast_auto_task() -> dict:
    """Beat-задача (ежедневно): 1-го числа ставит рассылку всем премиум-астрологам
    с включённой автоотправкой. В остальные дни — ничего."""
    from datetime import date

    if date.today().day != 1:
        return {"skipped": "not first of month"}

    from backend.models import AstrologerProfile, User

    db = SessionLocal()
    try:
        rows = (
            db.query(AstrologerProfile.id)
            .join(User, AstrologerProfile.user_id == User.id)
            .filter(AstrologerProfile.broadcast_auto == True)  # noqa: E712
            .filter(User.tier == "premium")
            .all()
        )
        ids = [r[0] for r in rows]
    finally:
        db.close()

    for aid in ids:
        send_client_broadcast_task.delay(aid, None, None, "template")

    logger.info("send_broadcast_auto_task: queued %d astrologers", len(ids))
    return {"queued_astrologers": len(ids)}


# ═══════════════════════════════════════════════════════════
# SUBSCRIPTIONS
# ═══════════════════════════════════════════════════════════

@celery_app.task(name="tasks.expire_subscriptions")
def expire_subscriptions() -> dict:
    """Истёкшая подписка → тариф падает до free.

    Оплата разовая, на 30 дней (backend/payments/common.activate_subscription),
    автопродления у ЮKassa мы не подключаем. До появления этой задачи джоба,
    понижающего tier по истечении current_period_end, в системе не было вовсе
    (кроме пилотного backend/pilot/cron.py) — то есть один платёж давал платный
    тариф навсегда.

    Карты сверх лимита free при этом НЕ удаляются и остаются доступны: проверка
    в POST /chart/calculate (main.py) слотовая — `total_charts >= profiles_limit`,
    то есть новый слот просто не выдаётся, пока карт не станет меньше лимита
    free. Отдельного кода для этого случая не требуется.

    Пилотных участников задача не трогает: у них нет записи в subscriptions,
    их даунгрейдом занимается backend/pilot/cron.py. Ручная выдача тарифа
    админкой ставит срок на 10 лет и сюда тоже не попадает.
    """
    from backend.models import Subscription, User

    db = SessionLocal()
    try:
        now = utcnow()
        rows = (
            db.query(Subscription, User)
            .join(User, User.id == Subscription.user_id)
            .filter(
                Subscription.status == "active",
                Subscription.current_period_end.isnot(None),
                Subscription.current_period_end < now,
            )
            .all()
        )
        for sub, user in rows:
            logger.info(
                "Subscription expired: user=%s tier=%s until=%s → free",
                user.id, user.tier, sub.current_period_end,
            )
            sub.status = "expired"
            sub.tier = "free"
            user.tier = "free"
        if rows:
            db.commit()
        return {"expired": len(rows)}
    finally:
        db.close()
