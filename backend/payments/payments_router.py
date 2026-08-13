"""Robokassa payments router.

Endpoints:
  POST /api/v1/payments/checkout          — создать ссылку на оплату
  POST /api/v1/payments/robokassa/result  — вебхук от Robokassa
  GET  /api/v1/payments/subscription      — текущая подписка
  POST /api/v1/payments/admin/set-tier    — принудительно сменить тариф (только для ADMIN_EMAIL)
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status, Form
from fastapi.responses import PlainTextResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.admin.admin_router import require_admin
from backend.database import get_db
from backend.limiter import client_ip
from backend.models import AdminAuditLog, User, Subscription, PaymentEvent, Partner
from backend.notifications.telegram import send_support_message
from backend.schemas import CheckoutRequest, CheckoutResponse, SubscriptionResponse
from backend.auth.dependencies import get_current_user
from backend.payments.robokassa_service import (
    create_payment_url,
    verify_payment,
    activate_subscription,
    apply_referral_reward,
    TIER_PRICES,
)
from backend.partners.commission import credit_commission

logger = logging.getLogger("astro.payments")

router = APIRouter(prefix="/api/v1/payments", tags=["payments"])


async def _alert_payment_failure(inv_id: str, user_id: str, tier: str, period: str, *, stage: str) -> None:
    """Живой человек должен узнать о зависшем платеже в течение часа, не из
    жалобы пользователя. Тот же канал, что уже используется для отзывов
    (см. backend/notifications/telegram.py) — недоступность Telegram здесь не
    страшна, send_support_message сама глотает исключение и просто пишет в лог.
    """
    text = (
        "🔴 Robokassa: платёж принят, но не превратился в подписку.\n"
        f"Стадия сбоя: {stage}\n"
        f"InvId={inv_id} user_id={user_id} tier={tier} period={period}\n"
        "Деньги списаны (подпись и сумма проверены). Проверить вручную "
        "и при необходимости выдать тариф через /admin/set-tier."
    )
    await send_support_message(text)


# ── Checkout ───────────────────────────────────────────────

@router.post("/checkout", response_model=CheckoutResponse)
async def checkout(
    data: CheckoutRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if data.tier not in ("lite", "pro", "premium"):
        raise HTTPException(400, "Tier must be 'lite', 'pro' or 'premium'.")

    if user.tier == data.tier:
        raise HTTPException(400, f"Вы уже на тарифе {data.tier}.")

    try:
        url = create_payment_url(user=user, tier=data.tier, billing_period=data.billing_period)
    except ValueError as e:
        raise HTTPException(400, str(e))

    return CheckoutResponse(checkout_url=url)


# ── Stripe webhook (legacy — kept for tests) ──────────────

# Legacy Stripe webhook удалён: провайдер — Robokassa. Маршрут закрыт, чтобы не
# держать неиспользуемую платёжную поверхность. При необходимости вернуть —
# восстановить из истории git вместе с backend/payments/stripe_service.py.


# ── Robokassa webhook ──────────────────────────────────────

@router.post("/robokassa/result", include_in_schema=False)
async def robokassa_result(request: Request, db: Session = Depends(get_db)):
    """
    Robokassa вызывает этот URL после успешной оплаты.
    Ответ должен быть строго: OK{InvId}
    """
    form = dict(await request.form())
    inv_id = form.get("InvId", "")

    valid, user_id, tier, period = verify_payment(form)

    if not valid:
        logger.warning("Robokassa: invalid signature, InvId=%s", inv_id)
        return PlainTextResponse("bad signature", status_code=400)

    if not user_id or not tier:
        logger.warning("Robokassa: missing Shp params, InvId=%s", inv_id)
        return PlainTextResponse("missing params", status_code=400)

    # Сверка суммы: подпись Robokassa покрывает OutSum, но добавляем проверку
    # соответствия ожидаемой цене тарифа как defense-in-depth.
    expected = TIER_PRICES.get((tier, period))
    try:
        paid = float(form.get("OutSum", "0"))
    except ValueError:
        paid = -1.0
    if expected is None or abs(paid - float(expected)) > 0.01:
        logger.warning(
            "Robokassa: amount mismatch InvId=%s tier=%s period=%s paid=%s expected=%s",
            inv_id, tier, period, paid, expected,
        )
        return PlainTextResponse("amount mismatch", status_code=400)

    # Идемпотентность / anti-replay в БД: уникальный inv_id. Раньше ключ жил
    # только в Redis, и при его недоступности код шёл дальше (fail-open) — тот же
    # вебхук с валидной подписью продлевал подписку сколько угодно раз.
    #
    # Запись о платеже и сама активация обязаны быть ОДНОЙ транзакцией.
    # Если закоммитить payment_events отдельно и упасть на активации, то повтор
    # вебхука увидит существующий inv_id, отчитается "OK" и уйдёт — деньги
    # списаны, подписки нет, и починить это уже нечем: ретраи исчерпаны.
    # Поэтому здесь flush (проверка уникальности без фиксации), затем активация,
    # и только потом общий commit.
    try:
        payment_event = PaymentEvent(
            provider="robokassa",
            inv_id=str(inv_id),
            user_id=user_id,
            tier=tier,
            period=period,
            amount=paid,
        )
        db.add(payment_event)
        db.flush()
    except IntegrityError:
        db.rollback()
        logger.info("Robokassa: duplicate InvId=%s ignored", inv_id)
        return PlainTextResponse(f"OK{inv_id}")
    except Exception:
        db.rollback()
        logger.exception("Robokassa: payment_events insert failed, InvId=%s", inv_id)
        # Валидный платёж (подпись и сумма уже проверены) не превратился в
        # запись — если ретраи Robokassa (у неё их конечное число) исчерпаются
        # раньше, чем БД оживёт, деньги списаны, а подписки не будет, и никакого
        # следа об этом нигде не останется. Алерт должен прийти живому человеку
        # в течение часа, а не всплыть через жалобу пользователя.
        await _alert_payment_failure(inv_id, user_id, tier, period, stage="payment_events insert")
        # 500 без активации: Robokassa повторит вызов, и повтор пройдёт штатно —
        # записи в payment_events не осталось, так что дублем он не считается.
        return PlainTextResponse("internal error", status_code=500)

    # Партнёрская комиссия и обычная реферальная награда («2 недели Pro за
    # друга») не должны иметь возможности сорвать реальный платёж. Голого
    # try/except здесь недостаточно: если код внутри падал уже после
    # db.add()/запроса, сессия SQLAlchemy оставалась в состоянии, требующем
    # rollback, и следующий шаг (activate_subscription, тот же db.commit())
    # валился следом за ней — платёж откатывался целиком, хотя try/except
    # формально стоял на месте. begin_nested() — SAVEPOINT: при сбое
    # откатывается только он, уже сфлашенный payment_event остаётся цел.
    #
    # Комиссия и обычная награда взаимоисключающие для одного реферера —
    # партнёрская программа отдельная сущность, не смешивается с обычной
    # реферальной механикой (Этап 2/3): если реферер — активный партнёр,
    # он получает комиссию деньгами, а не 2 недели подписки в подарок.
    try:
        with db.begin_nested():
            buyer = db.query(User).filter(User.id == user_id).first()
            if buyer and buyer.referred_by:
                is_active_partner = db.query(Partner.id).filter(
                    Partner.user_id == buyer.referred_by, Partner.status == "active",
                ).first() is not None
                if is_active_partner:
                    credit_commission(db, payment_event, buyer)
                else:
                    apply_referral_reward(buyer.referred_by, db)
    except Exception:
        logger.exception("Robokassa: referral reward/commission failed, InvId=%s", inv_id)

    try:
        activate_subscription(user_id=user_id, tier=tier, period=period, db=db)
    except Exception:
        # Откатывает и активацию, и запись о платеже — ретрай Robokassa начнёт
        # с чистого листа, а не упрётся в «уже обработано».
        db.rollback()
        logger.exception("Robokassa: activate_subscription failed")
        await _alert_payment_failure(inv_id, user_id, tier, period, stage="activate_subscription")
        return PlainTextResponse("internal error", status_code=500)

    logger.info("Robokassa: payment OK, InvId=%s user=%s tier=%s", inv_id, user_id, tier)
    return PlainTextResponse(f"OK{inv_id}")


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
