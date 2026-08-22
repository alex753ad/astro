"""ЮKassa: создание платежа и приём уведомлений.

Провайдер-специфичная часть. Всё, что не зависит от провайдера
(идемпотентность по payment_id, партнёрская комиссия / реферальная награда,
активация подписки в одной транзакции с записью платежа), живёт в
backend/payments/common.process_payment — здесь оно не дублируется.

Модель оплаты: разовый платёж на 30 дней, автопродления нет. Срок считает
activate_subscription: повторная оплата ТОГО ЖЕ тарифа суммируется (заплативший
дважды получает 60 дней), смена тарифа и оплата после истечения — отсчёт от
сегодня, остаток сгорает. Падение до free по истечении срока — задача
tasks.expire_subscriptions.

Endpoints:
  POST /api/v1/payments/checkout               — создать платёж, вернуть ссылку
  POST /api/v1/payments/yookassa/notification  — вебхук ЮKassa

Аутентификация вебхука. ЮKassa уведомления НЕ подписывает — единственная
проверка отправителя это его IP, поэтому:
  1) IP сверяется со списком подсетей ЮKassa (см. YOOKASSA_NETWORKS);
  2) телу запроса всё равно не доверяем — сумма, статус и metadata
     перечитываются из API по GET /v3/payments/{id}.
Одной первой проверки мало: список подсетей публичный, а тело вебхука
подделывается целиком.
"""

from __future__ import annotations

import ipaddress
import logging
import uuid
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.auth.dependencies import get_current_user
from backend.config import get_settings
from backend.database import get_db
from backend.limiter import client_ip
from backend.models import PaymentEvent, Subscription, User
from backend.time_utils import utcnow
from backend.payments.common import (
    TIER_PRICES_RUB,
    DuplicatePayment,
    PaymentProcessingError,
    process_payment,
)

logger = logging.getLogger("astro.payments.yookassa")
settings = get_settings()

router = APIRouter(prefix="/api/v1/payments", tags=["payments"])

API_BASE = "https://api.yookassa.ru/v3"
PROVIDER = "yookassa"

# Орион (premium) в чекаут не выпускается: тариф отключён в интерфейсе
# (ProfilePage.jsx — кнопка «Скоро», OrionPage), и покупать его нечем.
# Цена в TIER_PRICES_RUB при этом есть — она нужна админке для MRR, но
# создавать по ней платёж нельзя, иначе кнопку можно «включить» запросом мимо
# интерфейса и продать то, чего мы не обслуживаем.
CHECKOUT_TIERS = ("lite", "pro")
PERIOD = "monthly"

# Подсети, с которых ЮKassa шлёт уведомления. Список публикуется в их
# документации и МЕНЯЕТСЯ без предупреждения — держим его одной константой с
# датой сверки, а не россыпью по коду.
#   https://yookassa.ru/developers/using-api/webhooks
# Сверено: 21.08.2026.
# Если платежи однажды перестанут активироваться — первым делом сверить список
# заново: отказ по IP пишет в лог ERROR с адресом и этой датой, чтобы причина
# не выглядела как «просто 403 в nginx».
YOOKASSA_IP_LIST_CHECKED = "2026-08-21"
YOOKASSA_NETWORKS = [
    ipaddress.ip_network(net)
    for net in (
        "185.71.76.0/27",
        "185.71.77.0/27",
        "77.75.153.0/25",
        "77.75.156.11/32",
        "77.75.156.35/32",
        "77.75.154.128/25",
        "2a02:5180::/32",
    )
]


# ── Вспомогательное ────────────────────────────────────────

def _configured() -> bool:
    return bool(settings.yookassa_shop_id and settings.yookassa_secret_key)


def _auth() -> tuple[str, str]:
    return (settings.yookassa_shop_id, settings.yookassa_secret_key)


def _is_yookassa_ip(raw: str) -> bool:
    try:
        ip = ipaddress.ip_address(raw.strip())
    except ValueError:
        return False
    return any(ip in net for net in YOOKASSA_NETWORKS)


async def _fetch_payment(payment_id: str) -> dict[str, Any] | None:
    """Перечитать платёж из API ЮKassa. None — не удалось (сеть/5xx)."""
    try:
        async with httpx.AsyncClient(timeout=20.0) as http:
            resp = await http.get(f"{API_BASE}/payments/{payment_id}", auth=_auth())
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        logger.warning("YooKassa: не удалось перечитать платёж %s: %s", payment_id, exc)
        return None


def _amount_value(obj: dict[str, Any]) -> float:
    try:
        return float((obj.get("amount") or {}).get("value") or 0)
    except (TypeError, ValueError):
        return 0.0


# ── Checkout ───────────────────────────────────────────────

class CheckoutRequest(BaseModel):
    tier: str
    billing_period: str = PERIOD

    # Фронт присылает ещё success_url/cancel_url/promo_code — принимаем и
    # игнорируем. return_url всегда наш (/profile), иначе после оплаты можно
    # увести пользователя куда угодно чужим запросом. Промокоды в v1 не
    # поддерживаются намеренно: это вторая точка, где сумма платежа могла бы
    # разойтись с тем, что реально списала ЮKassa.
    model_config = {"extra": "ignore"}


@router.post("/checkout")
async def create_checkout(
    body: CheckoutRequest,
    user: User = Depends(get_current_user),
):
    tier = (body.tier or "").strip().lower()

    if tier == "premium":
        raise HTTPException(
            status_code=400,
            detail="Тариф Орион пока не продаётся. Напишите нам, если он вам нужен.",
        )
    if tier not in CHECKOUT_TIERS:
        raise HTTPException(
            status_code=400,
            detail=f"Неизвестный тариф. Доступны: {', '.join(CHECKOUT_TIERS)}.",
        )
    if body.billing_period != PERIOD:
        raise HTTPException(status_code=400, detail="Поддерживается только помесячная оплата.")
    if not _configured():
        logger.error("YooKassa: checkout вызван при незаданных YOOKASSA_SHOP_ID/SECRET_KEY")
        raise HTTPException(status_code=503, detail="Оплата временно недоступна.")

    from backend.email_service import TIER_NAMES

    amount = TIER_PRICES_RUB[tier]
    payload: dict[str, Any] = {
        "amount": {"value": f"{amount:.2f}", "currency": "RUB"},
        "capture": True,
        "confirmation": {
            "type": "redirect",
            "return_url": f"{settings.frontend_url}/profile",
        },
        "description": f"Astrea Timeline — {TIER_NAMES.get(tier, tier.capitalize())}, 30 дней",
        # metadata возвращается в вебхуке и перечитывается из API — это
        # единственный способ понять, за кого и за какой тариф пришли деньги.
        "metadata": {"user_id": str(user.id), "tier": tier, "period": PERIOD},
        # Блока "receipt" здесь нет и не будет — это не недоделка.
        #
        # ЮKassa закрыла сервис «Чеки для самозанятых» 29.12.2025 (ответ их
        # поддержки, 22.08.2026). Чек по НПД теперь не сформировать ни через
        # личный кабинет, ни передачей receipt в API: передавать его просто
        # некуда. Доход владелец регистрирует вручную в приложении «Мой налог».
        #
        # Чтобы делать это не заглядывая в кабинет ЮKassa, вебхук шлёт
        # владельцу в Telegram всё нужное для проведения дохода — см.
        # _notify_payment ниже.
        #
        # Автоматизация возможна только через API ФНС напрямую, мимо ЮKassa, —
        # отдельная задача, см. CLAUDE.md.
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as http:
            resp = await http.post(
                f"{API_BASE}/payments",
                json=payload,
                auth=_auth(),
                # Ключ идемпотентности ЮKassa: при ретрае с тем же ключом
                # вернётся тот же платёж, а не второй такой же.
                headers={"Idempotence-Key": str(uuid.uuid4())},
            )
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        logger.exception("YooKassa: создание платежа не удалось, user=%s tier=%s", user.id, tier)
        raise HTTPException(status_code=502, detail="Платёжный сервис недоступен, попробуйте позже.")

    checkout_url = (data.get("confirmation") or {}).get("confirmation_url")
    if not checkout_url:
        logger.error("YooKassa: в ответе нет confirmation_url: %s", data)
        raise HTTPException(status_code=502, detail="Платёжный сервис вернул неожиданный ответ.")

    logger.info(
        "YooKassa: checkout создан payment_id=%s user=%s tier=%s amount=%s",
        data.get("id"), user.id, tier, amount,
    )
    return {"checkout_url": checkout_url, "payment_id": data.get("id")}


# ── Вебхук ─────────────────────────────────────────────────

@router.post("/yookassa/notification")
async def yookassa_notification(request: Request, db: Session = Depends(get_db)):
    """Приём уведомлений ЮKassa.

    Ответ 200 означает «доставлено», и ЮKassa прекращает ретраи. Поэтому 200
    отдаётся и на уже обработанное событие, и на событие, которое нас не
    касается — иначе доставка будет повторяться до истечения суток. 5xx
    остаётся только для случаев, когда ретрай действительно нужен (не смогли
    проверить платёж, не смогли активировать подписку).
    """
    ip = client_ip(request)
    if not _is_yookassa_ip(ip):
        logger.error(
            "YooKassa webhook отклонён: IP %s не входит в список подсетей ЮKassa "
            "(сверен %s, backend/payments/yookassa_router.py:YOOKASSA_NETWORKS). "
            "Если платежи перестали активироваться — сверьте список заново: "
            "https://yookassa.ru/developers/using-api/webhooks",
            ip, YOOKASSA_IP_LIST_CHECKED,
        )
        raise HTTPException(status_code=403, detail="forbidden")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="malformed body")
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="malformed body")

    event = body.get("event")
    obj = body.get("object") or {}
    obj_id = str(obj.get("id") or "")
    if not obj_id:
        logger.error("YooKassa webhook без object.id: event=%s", event)
        raise HTTPException(status_code=400, detail="no object.id")

    if event == "refund.succeeded":
        return await _handle_refund(db, obj)

    if event == "payment.canceled":
        # Ничего не меняем: подписки по неоплаченному платежу и не было.
        logger.info("YooKassa: payment.canceled id=%s", obj_id)
        return {"ok": True}

    if event != "payment.succeeded":
        logger.info("YooKassa: событие %s не обрабатывается, id=%s", event, obj_id)
        return {"ok": True}

    return await _handle_succeeded(db, obj_id)


async def _handle_succeeded(db: Session, payment_id: str) -> dict[str, Any]:
    payment = await _fetch_payment(payment_id)
    if payment is None:
        # Проверить платёж не смогли — активировать по неподписанному телу
        # вебхука нельзя. 500, чтобы ЮKassa повторила доставку.
        raise HTTPException(status_code=500, detail="verification failed")

    if payment.get("status") != "succeeded":
        # Тело вебхука говорило одно, API — другое. Ретрай не поможет.
        logger.error(
            "YooKassa: вебхук payment.succeeded, но API отдаёт status=%s для %s",
            payment.get("status"), payment_id,
        )
        return {"ok": True}

    meta = payment.get("metadata") or {}
    user_id = str(meta.get("user_id") or "")
    tier = str(meta.get("tier") or "")
    period = str(meta.get("period") or PERIOD)

    if not user_id or tier not in CHECKOUT_TIERS:
        logger.error("YooKassa: непригодная metadata у платежа %s: %s", payment_id, meta)
        raise HTTPException(status_code=400, detail="bad metadata")

    paid = _amount_value(payment)
    expected = TIER_PRICES_RUB[tier]
    if abs(paid - expected) > 0.01:
        logger.error(
            "YooKassa: сумма платежа %s не совпадает с ценой тарифа %s: %s ≠ %s — подписка НЕ выдана",
            payment_id, tier, paid, expected,
        )
        raise HTTPException(status_code=400, detail="amount mismatch")

    try:
        process_payment(
            db,
            provider=PROVIDER,
            payment_id=payment_id,
            user_id=user_id,
            tier=tier,
            period=period,
            amount=paid,
        )
    except DuplicatePayment:
        # Ретрай ЮKassa или повтор перехваченного запроса. Ровно тот же ответ,
        # что и на первую успешную доставку — иначе ретраи не прекратятся.
        logger.info("YooKassa: повторная доставка payment_id=%s, пропущено", payment_id)
        return {"ok": True}
    except PaymentProcessingError as exc:
        logger.error("YooKassa: обработка платежа %s упала на шаге %s", payment_id, exc.stage)
        raise HTTPException(status_code=500, detail="processing failed")

    # Только после успешной обработки: на повторной доставке сюда не доходим
    # (DuplicatePayment вернул выше), поэтому одно сообщение на один платёж.
    await _notify_payment(db, payment_id, user_id, tier, paid)
    return {"ok": True}


async def _notify_payment(db: Session, payment_id, user_id, tier, amount) -> None:
    """Сообщить владельцу о поступившем платеже — для «Мой налог».

    Не дублирует кабинет ЮKassa, а заменяет поход в него: ЮKassa закрыла
    сервис «Чеки для самозанятых» 29.12.2025, и доход по НПД регистрируется
    вручную в приложении. Здесь собрано ровно то, что нужно ввести: сумма,
    дата и от кого. Без этого пришлось бы сверять кабинет со своей базой.

    Молчит и не мешает ответить 200, если Telegram недоступен или не задан
    TELEGRAM_SUPPORT_CHAT_ID: провал уведомления не повод заставлять ЮKassa
    ретраить уже обработанный платёж.
    """
    from backend.email_service import TIER_NAMES
    from backend.notifications.telegram import send_support_message

    try:
        buyer = db.query(User).filter(User.id == user_id).first()
        sub = (
            db.query(Subscription)
            .filter(Subscription.user_id == user_id)
            .order_by(Subscription.current_period_end.desc().nullslast())
            .first()
        )
        until = (
            sub.current_period_end.strftime("%d.%m.%Y")
            if sub and sub.current_period_end else "—"
        )
        text = (
            f"💰 Оплата {amount:.2f} ₽ — {TIER_NAMES.get(tier, tier)}\n"
            f"Дата: {utcnow().strftime('%d.%m.%Y %H:%M')} UTC\n"
            f"Плательщик: {buyer.email if buyer else user_id}\n"
            f"Подписка действует до: {until}\n"
            f"payment_id: {payment_id}\n\n"
            f"⚠️ Провести доход вручную в «Мой налог» — ЮKassa чеки для "
            f"самозанятых не формирует с 29.12.2025."
        )
        await send_support_message(text)
    except Exception:
        logger.warning("YooKassa: не удалось отправить уведомление о платеже %s", payment_id)


async def _handle_refund(db: Session, obj: dict[str, Any]) -> dict[str, Any]:
    """Возврат — только фиксируем и уведомляем владельца.

    Доступ НЕ отзываем сознательно. Оплата разовая, возврат почти всегда
    частичный или по договорённости, и решение принимает владелец, а не
    автомат: автоматический отзыв по вебхуку отобрал бы у человека то, о чём
    с ним, возможно, только что договорились. Отзыв, если он нужен, делается
    руками — POST /api/v1/admin/payments/{id}/refund (снимает партнёрскую
    комиссию) и /api/v1/payments/admin/set-tier.
    """
    refund_id = str(obj.get("id"))
    payment_id = str(obj.get("payment_id") or "")
    amount = _amount_value(obj)

    # Идемпотентность на той же таблице, что и платежи. Префикс обязателен:
    # без него id возврата мог бы совпасть с id платежа в том же уникальном
    # индексе.
    #
    # Дедупликация — ТОЛЬКО уникальный индекс inv_id, никакого SELECT «а нет ли
    # уже такой записи» перед вставкой: ЮKassa ретраит refund.succeeded так же,
    # как остальные события, и два параллельных ретрая прошли бы такую проверку
    # оба. Второй INSERT блокируется на индексе до коммита первого и падает
    # IntegrityError.
    #
    # Порядок здесь несущий: запись коммитится ДО уведомления, поэтому дубль
    # уходит по ветке IntegrityError и второго сообщения в Telegram не будет.
    # Если однажды понадобится уведомлять раньше — сначала придумать, чем
    # заменить эту гарантию. Запрос origin ниже дедупликацией не является: он
    # идёт по другому ключу (inv_id исходного платежа) и нужен только чтобы
    # проставить user/tier.
    inv_id = f"refund:{refund_id}"
    origin = (
        db.query(PaymentEvent).filter(PaymentEvent.inv_id == payment_id).first()
        if payment_id else None
    )

    try:
        db.add(PaymentEvent(
            provider=PROVIDER,
            inv_id=inv_id,
            user_id=origin.user_id if origin else None,
            tier=origin.tier if origin else None,
            period=origin.period if origin else None,
            # Минус: в выгрузке платежей пользователя (profile/router.py)
            # возврат иначе выглядел бы вторым платежом.
            amount=-amount,
        ))
        db.commit()
    except IntegrityError:
        db.rollback()
        logger.info("YooKassa: повторная доставка refund_id=%s, пропущено", refund_id)
        return {"ok": True}

    logger.warning(
        "YooKassa: возврат %s по платежу %s на %s ₽ (user=%s) — подписка не тронута, "
        "отзыв доступа при необходимости делается вручную",
        refund_id, payment_id or "?", amount, origin.user_id if origin else "?",
    )

    await _notify_refund(refund_id, payment_id, amount, origin)
    return {"ok": True}


async def _notify_refund(refund_id, payment_id, amount, origin) -> None:
    """Уведомление в служебный чат. Недоступность Telegram не должна мешать
    ответить ЮKassa 200 — иначе ретраи пойдут по кругу из-за чата поддержки
    (send_support_message и сам глотает ошибки, try/except здесь — на случай,
    если не задан токен и импорт/вызов упадёт иначе)."""
    from backend.notifications.telegram import send_support_message

    text = (
        f"↩️ ЮKassa: возврат {amount:.2f} ₽\n"
        f"refund_id: {refund_id}\n"
        f"payment_id: {payment_id or '—'}\n"
        f"user_id: {origin.user_id if origin else '—'}\n"
        f"tier: {origin.tier if origin else '—'}\n\n"
        f"Подписка НЕ отозвана. Если доступ нужно закрыть — админка: "
        f"refund комиссии по платежу и set-tier free."
    )
    try:
        await send_support_message(text)
    except Exception:
        logger.warning("YooKassa: не удалось отправить уведомление о возврате %s", refund_id)
