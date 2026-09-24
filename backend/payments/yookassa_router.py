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
from backend.limiter import client_ip, limiter
from backend.models import PaymentEvent, Subscription, User
from backend.redis_client import get_redis
from backend.time_utils import utcnow
from backend.payments.common import (
    TIER_PRICES_RUB,
    DuplicatePayment,
    PaymentProcessingError,
    SubscriptionOwnerMissing,
    price_on,
    process_payment,
)
from backend.payments.receipts import notify_receipt, paid_at_from

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


# Троттлинг уведомлений об отказе по IP. ЮKassa ретраит доставку, а сломавшийся
# фильтр отбивает подряд всё — без окна владелец получит сотни сообщений и
# перестанет их читать. Счётчик в Redis, а не в памяти процесса: перезапуск
# контейнера не должен открывать окно заново.
_IP_REJECT_NOTIFY_KEY = "yookassa:ip_reject_notified"
_IP_REJECT_COUNT_KEY = "yookassa:ip_reject_count"
_IP_REJECT_WINDOW_SEC = 3600


async def _notify_ip_reject(ip: str) -> None:
    """Сообщить владельцу, что вебхук отбит по IP — не чаще раза в час.

    Зачем: отказ виден только в логе контейнера, а логи не переживают деплой.
    Если список подсетей ЮKassa устареет, изменится docker-сеть или сломается
    определение IP, платежи начнут молча не активироваться — деньги списаны,
    подписки нет, узнать неоткуда.

    Тело запроса намеренно НЕ пересылается: там платёжные данные, а чат
    служебный. Уходит только адрес отправителя, число отказов за окно и дата
    последней сверки списка подсетей.

    Молчит при недоступности Redis (без счётчика нечем сдержать лавину —
    предпочитаем не уведомить, чем завалить чат) и при незаданном
    TELEGRAM_SUPPORT_CHAT_ID, как и _notify_payment. Ни то, ни другое не
    меняет ответ вебхука: как отвечали 403, так и отвечаем.
    """
    from backend.notifications.telegram import send_support_message

    try:
        redis = get_redis()
        rejected = await redis.incr(_IP_REJECT_COUNT_KEY)
        if rejected == 1:
            await redis.expire(_IP_REJECT_COUNT_KEY, _IP_REJECT_WINDOW_SEC)
        # SET NX: окно занимает ровно один запрос, даже если отказы пришли
        # одновременно в несколько соединений.
        claimed = await redis.set(
            _IP_REJECT_NOTIFY_KEY, "1", ex=_IP_REJECT_WINDOW_SEC, nx=True
        )
        if not claimed:
            return
        # Следующее окно считает с нуля — в сообщении будет число за период,
        # а не с начала времён.
        await redis.delete(_IP_REJECT_COUNT_KEY)
    except Exception as exc:
        logger.warning(
            "YooKassa: троттлинг уведомления об отказе по IP недоступен, "
            "сообщение не отправлено: %s", exc,
        )
        return

    text = (
        "🚫 ЮKassa: вебхук отбит по IP-фильтру\n"
        f"Отправитель: {ip}\n"
        f"Отказов за последний час: {rejected}\n"
        f"Список подсетей сверялся: {YOOKASSA_IP_LIST_CHECKED}\n"
        f"Время: {utcnow().strftime('%d.%m.%Y %H:%M')} UTC\n\n"
        "⚠️ Если это была сама ЮKassa, а не чужой запрос — платежи сейчас НЕ "
        "активируются: деньги списываются, подписка не выдаётся. Сверьте "
        "список подсетей (yookassa.ru/developers/using-api/webhooks) и "
        "TRUSTED_PROXY_IPS."  # вы-разрешено: уведомление владельцу
    )
    try:
        await send_support_message(text)
    except Exception:
        logger.warning("YooKassa: не удалось отправить уведомление об отказе по IP")


# ── Checkout ───────────────────────────────────────────────

class CheckoutRequest(BaseModel):
    tier: str
    billing_period: str = PERIOD
    # Откуда оплата: "app" — приложение создаёт платёж само и открывает
    # страницу ЮKassa во внешнем браузере (решение владельца 24.09.2026).
    # Влияет только на страницу возврата: из браузера человека просим
    # вернуться в приложение, а не показываем веб-профиль.
    source: str = "web"

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
            detail="Тариф Орион пока не продаётся. Напиши нам, если он тебе нужен.",
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

    # Цена на сегодня по расписанию: объявленная смена вступает в силу сама,
    # в свою дату, без деплоя в этот день (common.PRICE_SCHEDULE).
    amount = price_on(tier)
    payload: dict[str, Any] = {
        "amount": {"value": f"{amount:.2f}", "currency": "RUB"},
        "capture": True,
        "confirmation": {
            "type": "redirect",
            # Страница возврата сама спрашивает статус (GET /payments/status)
            # — вебхук может прийти и раньше редиректа, и через час.
            "return_url": f"{settings.frontend_url}/payment/return"
                          + ("?from=app" if body.source == "app" else ""),
        },
        "description": f"Aristea Timeline — {TIER_NAMES.get(tier, tier.capitalize())}, 30 дней",
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
        raise HTTPException(status_code=502, detail="Платёжный сервис недоступен, попробуй чуть позже.")

    checkout_url = (data.get("confirmation") or {}).get("confirmation_url")
    if not checkout_url:
        logger.error("YooKassa: в ответе нет confirmation_url: %s", data)
        raise HTTPException(status_code=502, detail="Платёжный сервис вернул неожиданный ответ.")

    logger.info(
        "YooKassa: checkout создан payment_id=%s user=%s tier=%s amount=%s",
        data.get("id"), user.id, tier, amount,
    )
    return {"checkout_url": checkout_url, "payment_id": data.get("id")}


# ── Статус платежа и история ───────────────────────────────

# Причины отмены ЮKassa (cancellation_details.reason) → текст человеку.
# Главное в каждом — деньги не списаны: отказ при оплате не оставляет
# списания, а человек в этот момент думает именно об этом.
CANCEL_REASON_RU = {
    "insufficient_funds": "На карте не хватило денег.",
    "card_expired": "Срок действия карты истёк.",
    "invalid_card_number": "Номер карты введён с ошибкой.",
    "invalid_csc": "Код CVC введён с ошибкой.",
    "3d_secure_failed": "Банк не подтвердил оплату кодом.",
    "call_issuer": "Банк отклонил оплату — позвони в свой банк.",
    "issuer_unavailable": "Банк не ответил — попробуй чуть позже.",
    "payment_method_limit_exceeded": "Превышен лимит по карте.",
    "payment_method_restricted": "Этот способ оплаты сейчас недоступен.",
    "country_forbidden": "Оплата картой этой страны недоступна.",
    "fraud_suspected": "Банк заподозрил мошенничество и отклонил оплату.",
    "general_decline": "Банк отклонил оплату без объяснения причины.",
    "expired_on_confirmation": "Оплата не была завершена вовремя.",
    "canceled_by_merchant": "Платёж отменён.",
    "internal_timeout": "Платёжный сервис не ответил вовремя.",
}
CANCEL_REASON_DEFAULT = "Оплата не прошла."


def _subscription_state(db: Session, user: User) -> dict[str, Any]:
    sub = (
        db.query(Subscription).filter(Subscription.user_id == user.id)
        .order_by(Subscription.current_period_end.desc().nullslast()).first()
    )
    end = sub.current_period_end if sub and sub.status == "active" else None
    return {"tier": user.tier, "active_until": end.isoformat() if end else None}


@router.get("/status/{payment_id}")
@limiter.limit("30/minute")
async def payment_status(
    request: Request,
    payment_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Что с платежом — для экрана ожидания в приложении и на вебе.

    `state`: `succeeded` (тариф включён, с датой окончания) | `pending` (ждём
    банк) | `canceled` (не прошло, `reason` — по-русски) | `unknown` (ЮKassa
    не ответила — экран предлагает проверить позже).

    ⚠️ Если ЮKassa говорит «оплачено», а нашей записи нет, ручка НАЧИСЛЯЕТ
    сама, тем же `settle_payment`, что и вебхук. Иначе человек, вернувшийся
    раньше вебхука, видел бы бесплатный тариф при списанных деньгах. Повтор
    безопасен: начисление идемпотентно по id платежа.
    """
    event = db.query(PaymentEvent).filter(PaymentEvent.inv_id == payment_id).first()
    if event is not None and event.user_id == user.id and event.period:
        return {"state": "succeeded", **_subscription_state(db, user)}

    payment = await _fetch_payment(payment_id)
    if payment is None:
        return {"state": "unknown", **_subscription_state(db, user)}
    # Чужой или несуществующий платёж — одинаково 404, чтобы по ручке нельзя
    # было проверять чужие id.
    if str((payment.get("metadata") or {}).get("user_id") or "") != str(user.id):
        raise HTTPException(status_code=404, detail="Платёж не найден.")

    status = payment.get("status")
    if status == "succeeded":
        try:
            outcome = await settle_payment(db, payment)
        except PaymentProcessingError:
            return {"state": "unknown", **_subscription_state(db, user)}
        db.refresh(user)
        if outcome in (ACTIVATED, DUPLICATE):
            return {"state": "succeeded", **_subscription_state(db, user)}
        # Деньги есть, а начислить нельзя (сумма, возврат…) — владелец уже
        # получил сигнал из settle_payment. Человеку — честно и с выходом.
        return {"state": "review", **_subscription_state(db, user)}
    if status == "canceled":
        reason = ((payment.get("cancellation_details") or {}).get("reason")) or ""
        return {"state": "canceled", "reason": CANCEL_REASON_RU.get(reason, CANCEL_REASON_DEFAULT),
                **_subscription_state(db, user)}
    return {"state": "pending", **_subscription_state(db, user)}


@router.get("/history")
async def payment_history(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Платежи и возвраты человека, новые сверху, плюс текущий тариф.

    Непригодные платежи (period NULL — сумма/валюта не сошлись) тоже
    показываются: деньги человек отдал, и строка «на проверке» честнее, чем
    отсутствие строки, — ровно с неё и начинается «заплатила, покупки нет».
    """
    rows = (
        db.query(PaymentEvent).filter(PaymentEvent.user_id == user.id)
        .order_by(PaymentEvent.created_at.desc()).limit(50).all()
    )
    items = []
    for r in rows:
        refund = str(r.inv_id).startswith("refund:") or (r.amount or 0) < 0
        items.append({
            "id": r.inv_id,
            "at": r.created_at.isoformat() if r.created_at else None,
            "tier": r.tier,
            "amount": abs(r.amount or 0),
            "kind": "refund" if refund else ("payment" if r.period else "review"),
        })
    return {"items": items, **_subscription_state(db, user)}


# ── Вебхук ─────────────────────────────────────────────────

@router.post("/yookassa/notification")
async def yookassa_notification(request: Request, db: Session = Depends(get_db)):
    """Приём уведомлений ЮKassa.

    Ответ 200 означает «доставлено», и ЮKassa прекращает ретраи. Поэтому 200
    отдаётся и на уже обработанное событие, и на событие, которое нас не
    касается — иначе доставка будет повторяться до истечения суток. 5xx
    остаётся только для случаев, когда ретрай действительно нужен (не смогли
    проверить платёж, не смогли обработать его технически).

    Правило разделения (аудит 23.08.2026, находки 2.1 и 2.9):
      • ПОСТОЯННАЯ причина → 200. Повтор гарантированно даст тот же результат,
        сутки ретраев только зашумят. Но 200 обязан оставлять след: платёж
        записывается в payment_events и владелец получает уведомление
        (_record_unusable_payment, _notify_orphan_payment).
      • ВРЕМЕННАЯ причина → 500, ретрай нужен: API ЮKassa недоступен,
        обработка упала технически.
    Единственное не-2xx на постоянную причину, оставленное намеренно, — 403 по
    IP: если список подсетей устареет и стучится настоящая ЮKassa, сутки
    ретраев дают окно, за которое список можно поправить, и платёж активируется
    сам. Плюс 400 на нечитаемое тело — там нет даже идентификатора платежа,
    записывать нечего.
    """
    ip = client_ip(request)
    if not _is_yookassa_ip(ip):
        logger.error(
            "YooKassa webhook отклонён: IP %s не входит в список подсетей ЮKassa "
            "(сверен %s, backend/payments/yookassa_router.py:YOOKASSA_NETWORKS). "
            "Если платежи перестали активироваться — сверьте список заново: "
            "https://yookassa.ru/developers/using-api/webhooks",  # вы-разрешено: лог для владельца
            ip, YOOKASSA_IP_LIST_CHECKED,
        )
        # Лог не переживает деплой — дублируем владельцу в Telegram (раз в час).
        await _notify_ip_reject(ip)
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
    try:
        await settle_payment(db, payment)
    except PaymentProcessingError:
        raise HTTPException(status_code=500, detail="processing failed")
    return {"ok": True}


# Итог settle_payment — чтобы вызывающий (сверка, ручка статуса) мог отличить
# «начислено сейчас» от «уже было» и от «не начисляется».
ACTIVATED = "activated"
DUPLICATE = "duplicate"
UNUSABLE = "unusable"
ORPHAN = "orphan"
NOT_SUCCEEDED = "not_succeeded"


def _parse_created_at(payment: dict[str, Any]):
    """created_at платежа из API ЮKassa (ISO, UTC) → aware datetime или None."""
    from datetime import datetime
    raw = str(payment.get("created_at") or "")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


async def settle_payment(db: Session, payment: dict[str, Any]) -> str:
    """Проверить уже ПЕРЕЧИТАННЫЙ из API платёж и начислить тариф.

    Единственный путь начисления — его зовут вебхук, ручка статуса
    (`GET /payments/status/{id}`) и ежедневная сверка (payments/reconcile.py).
    Проверки одни на всех, поэтому сверка начисляет ровно тогда, когда начислил
    бы вебхук (решение владельца 24.09.2026), и не шире.

    Возвращает один из итогов выше. PaymentProcessingError — временный сбой,
    его вызывающий обязан повторить (вебхук — 500).
    """
    payment_id = str(payment.get("id") or "")
    if payment.get("status") != "succeeded":
        if payment.get("status") not in ("pending", "waiting_for_capture", "canceled"):
            logger.error("YooKassa: платёж %s в статусе %s", payment_id, payment.get("status"))
        return NOT_SUCCEEDED

    meta = payment.get("metadata") or {}
    user_id = str(meta.get("user_id") or "")
    tier = str(meta.get("tier") or "")
    period = str(meta.get("period") or PERIOD)

    paid = _amount_value(payment)
    # Момент оплаты по ЮKassa — для чека «Мой налог» и месячной сводки
    # (payments/receipts.py). Не utcnow(): сверка начисляет с опозданием.
    paid_at = paid_at_from(payment)

    # Непригодная metadata — постоянная причина: она фиксируется при создании
    # платежа и при перечитывании всегда та же. Сюда же попадает оплаченный
    # premium (Орион в чекаут не выпускается) — деньги за тариф, который мы не
    # обслуживаем. Сырую metadata в лог кладём, в Telegram — нет.
    if not user_id or tier not in CHECKOUT_TIERS:
        logger.error("YooKassa: непригодная metadata у платежа %s: %s", payment_id, meta)
        problem = (
            f"тариф «{tier}» не продаётся или не распознан" if tier
            else "в metadata платежа нет user_id и тарифа"
        )
        await _record_unusable_payment(
            db, payment_id, problem=problem, amount=paid, paid_at=paid_at,
            user_id=user_id or None, tier=tier if tier in TIER_PRICES_RUB else None,
        )
        return UNUSABLE

    # По платежу уже был возврат — тариф за него не выдаём. Вебхук возврата
    # (refund.succeeded) подписку не трогает, но выдавать её по возвращённым
    # деньгам, если вебхук оплаты опоздал или платёж нашла сверка, нельзя.
    refunded = _amount_value({"amount": payment.get("refunded_amount") or {}})
    if refunded > 0:
        await _record_unusable_payment(
            db, payment_id, problem=f"по платежу уже был возврат {refunded:.2f} ₽",
            amount=paid, paid_at=paid_at, user_id=user_id, tier=tier,
        )
        return UNUSABLE

    # Цена — на момент СОЗДАНИЯ платежа, а не сегодняшняя: иначе повышение
    # цены отбросило бы платёж, созданный до него и оплаченный после
    # (common.PRICE_SCHEDULE). Нет created_at — сегодняшняя.
    expected = price_on(tier, _parse_created_at(payment))
    if expected is None or abs(paid - expected) > 0.01:
        return await _unusable(
            db, payment_id,
            problem=f"сумма не совпадает с ценой тарифа: заплачено {paid:.2f}, ожидалось {expected or 0:.2f}",
            amount=paid, paid_at=paid_at, user_id=user_id, tier=tier,
        )

    # Валюта — часть сверки суммы, а не отдельная проверка (аудит 23.08.2026,
    # находка 2.3). До этого читался только amount.value, и «790» в любой
    # валюте проходило как 790 ₽: цены в PRICE_SCHEDULE — рубли по определению.
    # Сегодня чекаут жёстко ставит RUB (см. create_checkout), поэтому путь
    # недостижим — но ровно эта проверка выстрелит первой, если в кабинете
    # ЮKassa включат мультивалютность или появится второй способ создать
    # платёж. Дешевле держать её, чем вспоминать про неё потом.
    currency = str((payment.get("amount") or {}).get("currency") or "")
    if currency != "RUB":
        return await _unusable(
            db, payment_id,
            problem=f"валюта {currency or 'не указана'}, а цены рублёвые",
            amount=paid, paid_at=paid_at, user_id=user_id, tier=tier, currency=currency or "?",
        )

    try:
        process_payment(
            db,
            provider=PROVIDER,
            payment_id=payment_id,
            user_id=user_id,
            tier=tier,
            period=period,
            amount=paid,
            paid_at=paid_at,
        )
    except DuplicatePayment:
        # Ретрай ЮKassa, повтор перехваченного запроса или вторая дорожка
        # (вебхук + ручка статуса + сверка). Ровно тот же ответ, что и на
        # первую успешную доставку — иначе ретраи не прекратятся.
        logger.info("YooKassa: повторная доставка payment_id=%s, пропущено", payment_id)
        return DUPLICATE
    except SubscriptionOwnerMissing as exc:
        # 200, а не 500: причина постоянная (пользователя нет), ретрай ЮKassa
        # сутки подряд ничего не исправит — только зашумит. Запись о платеже
        # при этом уже закоммичена в process_payment, деньги не пропали
        # бесследно. Дальше — руками, поэтому уведомление обязательно.
        logger.error(
            "YooKassa: платёж %s записан, но подписку выдать некому (user=%s)",
            payment_id, exc.user_id,
        )
        await _notify_orphan_payment(payment_id, exc.user_id, tier, paid)
        await notify_receipt(db, payment_id=payment_id, amount=paid, paid_at=paid_at, tier=tier,
                             user_id=None, note="Тариф не выдан: пользователя нет в базе (см. сообщение выше).")
        return ORPHAN
    except PaymentProcessingError as exc:
        logger.error("YooKassa: обработка платежа %s упала на шаге %s", payment_id, exc.stage)
        raise

    # Только после успешной обработки: на повторной доставке сюда не доходим
    # (DuplicatePayment вернул выше), поэтому одно сообщение на один платёж.
    await _notify_payment(db, payment_id, user_id, tier, paid, paid_at)
    return ACTIVATED


async def _unusable(db, payment_id, **kw) -> str:
    await _record_unusable_payment(db, payment_id, **kw)
    return UNUSABLE


async def _record_unusable_payment(
    db: Session,
    payment_id: str,
    *,
    problem: str,
    amount: float,
    user_id: str | None = None,
    tier: str | None = None,
    paid_at=None,
    currency: str = "RUB",
) -> dict[str, Any]:
    """Платёж пришёл, но выдать по нему нечего. Записать, сообщить, ответить 200.

    Сюда попадают ТОЛЬКО постоянные причины (аудит 23.08.2026, находка 2.9):
    сумма или валюта не сходятся с ценой тарифа, metadata непригодна. Раньше
    все они отвечали 400, а ЮKassa ретраит всё, что не 2xx — сутки запросов,
    каждый из которых заведомо кончится тем же отказом, потому что и платёж, и
    его metadata на стороне провайдера уже неизменны. Логика та же, что для
    SubscriptionOwnerMissing: постоянная причина → 200, временная → 500
    (недоступность API и сбой обработки по-прежнему отдают 500 и ретраятся).

    200 без следа было бы молчаливым проглатыванием платежа, поэтому:
      • запись в payment_events под тем же inv_id, что и обычный платёж —
        деньги пришли, след обязан остаться, а уникальный индекс заодно
        не даст обработать этот платёж повторно;
      • уведомление владельцу — разбираться руками.

    Порядок несущий, как и в _handle_refund: коммит ДО уведомления, поэтому
    параллельный ретрай уходит по ветке IntegrityError и второго сообщения в
    Telegram не будет.

    user_id/tier могут быть None (непригодная metadata) — колонки nullable.
    """
    try:
        db.add(PaymentEvent(
            provider=PROVIDER,
            inv_id=payment_id,
            user_id=user_id or None,
            tier=tier or None,
            period=None,
            amount=amount,
            paid_at=paid_at,
        ))
        db.commit()
    except IntegrityError:
        db.rollback()
        logger.info("YooKassa: повторная доставка непригодного платежа %s, пропущено", payment_id)
        return {"ok": True}

    logger.error(
        "YooKassa: платёж %s записан, но подписка НЕ выдана — %s", payment_id, problem,
    )
    await _notify_unusable_payment(payment_id, problem, amount, tier)
    # Деньги получены — чек нужен и без выданного тарифа (payments/receipts.py).
    await notify_receipt(db, payment_id=payment_id, amount=amount, paid_at=paid_at, tier=tier,
                         user_id=user_id, currency=currency,
                         note=f"Тариф не выдан: {problem} (см. сообщение выше).")
    return {"ok": True}


async def _notify_unusable_payment(payment_id, problem: str, amount: float, tier) -> None:
    """Сообщить владельцу о платеже, по которому ничего не выдано.

    Пятая тонкая обёртка над send_support_message — новый канал не заводится.
    Троттла нет по той же причине, что и у _notify_orphan_payment: это деньги
    и единичное событие, пропустить нельзя ни одного.

    Сырую metadata платежа сюда намеренно НЕ кладём (решение владельца
    23.08.2026): по payment_id всё остальное видно в кабинете ЮKassa, а состав
    полей metadata может измениться, и передача их в служебный чат политикой
    конфиденциальности не описана. Уходит только payment_id, сумма и тариф,
    если он вообще распознан.
    """
    from backend.email_service import TIER_NAMES
    from backend.notifications.telegram import send_support_message

    tier_line = f"Тариф: {TIER_NAMES.get(tier, tier)}\n" if tier else "Тариф: не распознан\n"
    text = (
        "⚠️ ЮKassa: платёж получен, подписка НЕ выдана\n"
        f"Причина: {problem}\n"
        f"Сумма платежа: {amount:.2f}\n"
        f"{tier_line}"
        f"Дата: {utcnow().strftime('%d.%m.%Y %H:%M')} UTC\n"
        f"payment_id: {payment_id}\n\n"
        "Платёж записан в payment_events, деньги не потерялись. Нужно два "
        "действия:\n"
        "1) Пробить чек в «Мой налог» — деньги получены, данные в следующем сообщении.\n"
        "2) Решить с доступом: выдать тариф через админку "
        "(/api/v1/payments/admin/set-tier) или вернуть деньги. Подробности "
        "платежа — по payment_id в кабинете ЮKassa."
    )
    try:
        await send_support_message(text)
    except Exception:
        logger.warning("YooKassa: не удалось отправить уведомление о непригодном платеже %s", payment_id)


async def _notify_orphan_payment(payment_id, user_id, tier, amount) -> None:
    """Деньги пришли, а активировать некому — владельцу нужны ОБА действия.

    Четвёртая тонкая обёртка над send_support_message (рядом с _notify_payment,
    _notify_refund, _notify_ip_reject) — новый канал не заводится.
    Переиспользовать _notify_payment напрямую нельзя: он говорит «💰 Оплата» и
    умалчивает, что подписки нет, — владелец решил бы, что всё прошло штатно.

    Троттла здесь намеренно НЕТ, в отличие от _notify_ip_reject: там гасится
    лавина одинаковых отказов, а тут каждое событие — отдельные деньги
    конкретного человека, пропустить нельзя ни одно.

    Как и остальные уведомления, ошибку проглатывает: недоступный Telegram не
    повод заставлять ЮKassa ретраить уже записанный платёж.
    """
    from backend.email_service import TIER_NAMES
    from backend.notifications.telegram import send_support_message

    text = (
        "⚠️ ЮKassa: платёж получен, но подписку выдать НЕКОМУ\n"
        f"Сумма: {amount:.2f} ₽ — {TIER_NAMES.get(tier, tier)}\n"
        f"Дата: {utcnow().strftime('%d.%m.%Y %H:%M')} UTC\n"
        f"user_id из платежа: {user_id} — такого пользователя нет в базе\n"
        f"payment_id: {payment_id}\n\n"
        "Платёж записан в payment_events, деньги не потерялись. Нужно два "
        "действия:\n"
        "1) Пробить чек в «Мой налог» — обязательно в любом случае, деньги "
        "получены. Данные для чека — в следующем сообщении.\n"
        "2) Разобраться с подпиской руками: скорее всего человек удалил "
        "аккаунт после оплаты. Если он вернётся — выдать тариф через админку "
        "(/api/v1/payments/admin/set-tier) или вернуть деньги."
    )
    try:
        await send_support_message(text)
    except Exception:
        logger.warning("YooKassa: не удалось отправить уведомление о платеже без владельца %s", payment_id)


async def _notify_payment(db: Session, payment_id, user_id, tier, amount, paid_at=None) -> None:
    """Сообщить владельцу о поступившем платеже — для «Мой налог».

    Не дублирует кабинет ЮKassa, а заменяет поход в него: ЮKassa закрыла
    сервис «Чеки для самозанятых» 29.12.2025, и доход по НПД регистрируется
    вручную в приложении. Здесь собрано ровно то, что нужно ввести: сумма,
    дата и от кого. Без этого пришлось бы сверять кабинет со своей базой.

    Молчит и не мешает ответить 200, если Telegram недоступен или не задан
    TELEGRAM_SUPPORT_CHAT_ID: провал уведомления не повод заставлять ЮKassa
    ретраить уже обработанный платёж.

    С 24.09.2026 это и есть сообщение-чек (payments/receipts.py): дата — момент
    ОПЛАТЫ по Москве, а не момент отправки, иначе платёж, начисленный сверкой
    через несколько дней, получил бы в чеке чужую дату.
    """
    try:
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
    except Exception:
        until = "—"
    await notify_receipt(db, payment_id=payment_id, amount=amount, paid_at=paid_at,
                         tier=tier, user_id=user_id, note=f"Тариф выдан, действует до {until}.")


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
        f"🧾 Чек по платежу {payment_id or '—'} в «Мой налог» — аннулировать "
        f"(«Возврат средств»), если он уже пробит.\n\n"
        f"Подписка НЕ отозвана. Если доступ нужно закрыть — админка: "
        f"refund комиссии по платежу и set-tier free."
    )
    try:
        await send_support_message(text)
    except Exception:
        logger.warning("YooKassa: не удалось отправить уведомление о возврате %s", refund_id)
