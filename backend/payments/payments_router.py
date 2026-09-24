"""Общие эндпоинты подписки — не привязаны к платёжному провайдеру.

Checkout и приём вебхука платежей удалены вместе с Robokassa/Stripe
(19.08.2026 — мёртвый код: аккаунтов не было, ни одного платежа не прошло).
Их место займёт роутер ЮKassa: провайдер-независимая часть (идемпотентность,
партнёрская комиссия/реферальная награда, активация подписки) уже готова в
backend/payments/common.process_payment — новому роутеру останется только
сверить подпись и сумму и вызвать эту функцию.

Endpoints:
  GET  /api/v1/payments/subscription      — текущая подписка
  POST /api/v1/payments/admin/set-tier    — принудительно сменить тариф (только для админов)
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from backend.admin.admin_router import require_admin
from backend.database import get_db
from backend.limiter import client_ip
from backend.models import AdminAuditLog, User, Subscription
from backend.schemas import SubscriptionResponse
from backend.auth.dependencies import get_current_user

logger = logging.getLogger("astro.payments")

router = APIRouter(prefix="/api/v1/payments", tags=["payments"])


# ── Admin: set tier ───────────────────────────────────────

@router.post("/admin/set-tier")
async def admin_set_tier(
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Принудительно сменить тариф без оплаты. Только для админов (users.is_admin).

    Раньше здесь был отдельный список из ADMIN_EMAIL — второй источник истины о
    правах помимо users.is_admin. Отзыв прав через is_admin=false не закрывал
    доступ владельцу почты из env, а сам эндпоинт выдаёт любой тариф на 10 лет.
    """
    from datetime import timedelta
    from backend.time_utils import utcnow

    body = await request.json()
    tier = body.get("tier", "")
    user_id = body.get("user_id")
    if tier not in ("free", "lite", "pro", "premium"):
        raise HTTPException(400, "tier must be: free, lite, pro, premium")

    # Если передан user_id — меняем тариф этому пользователю, иначе себе
    if user_id:
        target = db.query(User).filter(User.id == user_id).first()
        if not target:
            raise HTTPException(404, "User not found")
    else:
        target = admin

    previous_tier = target.tier
    target.tier = tier
    sub = db.query(Subscription).filter(Subscription.user_id == target.id).first()

    if tier == "free":
        if sub:
            sub.status = "canceled"
            sub.tier = "free"
    else:
        period_end = utcnow() + timedelta(days=3650)
        if sub:
            sub.tier = tier
            sub.status = "active"
            sub.current_period_end = period_end
        else:
            db.add(Subscription(
                user_id=target.id,
                stripe_price_id=f"admin_{tier}",
                status="active",
                tier=tier,
                current_period_end=period_end,
            ))

    # Аудит в БД, а не только в лог: docker-логи ротируются по 10 МБ, а выдача
    # премиума на 10 лет должна оставлять след, который переживёт ротацию.
    db.add(AdminAuditLog(
        admin_id=admin.id,
        admin_email=admin.email,
        action="set_tier",
        target_user_id=target.id,
        details={"tier": tier, "was": previous_tier},
        ip=client_ip(request),
    ))
    db.commit()
    logger.info("Admin set tier: admin=%s target=%s tier=%s", admin.id, target.id, tier)
    return {"ok": True, "tier": tier}


# ── Subscription info ──────────────────────────────────────

@router.get("/subscription", response_model=SubscriptionResponse)
async def get_subscription(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    sub = db.query(Subscription).filter(Subscription.user_id == user.id).first()
    return SubscriptionResponse(
        tier=user.tier,
        status=sub.status if sub else "none",
        stripe_subscription_id=None,
        current_period_end=sub.current_period_end.isoformat() if sub and sub.current_period_end else None,
    )


# ── Уведомление о смене цен (оферта п. 10.1) ───────────────

@router.post("/admin/price-notice")
async def admin_price_notice(
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Запуск уведомления о смене цен — только вручную, только админ.

    Тело: `{"effective_date": "YYYY-MM-DD", "dry_run": true}`. С `dry_run`
    (по умолчанию) ничего не отправляет и не публикует — отдаёт тему, текст и
    число адресатов, чтобы владелец увидел письмо до рассылки. Без него —
    публикует баннер и ставит рассылку в очередь (payments/price_notice.py).
    """
    from datetime import date as _date
    from backend.payments import price_notice as pn

    body = await request.json()
    try:
        effective = _date.fromisoformat(str(body.get("effective_date") or ""))
    except ValueError:
        raise HTTPException(422, "effective_date: YYYY-MM-DD")
    try:
        notice = pn.build_notice(effective)
    except pn.NoticeError as exc:
        raise HTTPException(422, str(exc))

    count = len(pn.recipients(db))
    if body.get("dry_run", True):
        return {"dry_run": True, "recipients": count, **notice}

    pn.publish(db, notice)
    db.add(AdminAuditLog(
        admin_id=admin.id, admin_email=admin.email, action="price_notice",
        target_user_id=None, details={"effective_date": notice["effective_date"], "recipients": count},
        ip=client_ip(request),
    ))
    db.commit()
    from backend.tasks import send_price_notice_task
    send_price_notice_task.delay(notice["effective_date"])
    logger.info("Price notice started: admin=%s effective=%s recipients=%d",
                admin.id, notice["effective_date"], count)
    return {"dry_run": False, "recipients": count, "published": True, **notice}


@router.get("/announcements")
async def active_announcements(db: Session = Depends(get_db)):
    """Действующие объявления для баннера — без входа: смена цен касается и
    тех, кто ещё не зарегистрирован, а публикация по оферте — для всех."""
    from backend.models import Announcement
    from backend.time_utils import utcnow
    rows = (db.query(Announcement).filter(Announcement.ends_at > utcnow())
            .order_by(Announcement.created_at.desc()).all())
    return {"items": [
        {"ref": r.ref, "title": r.title, "body": r.body, "link": r.link} for r in rows
    ]}
