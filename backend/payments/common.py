"""Провайдер-независимая логика обработки платежа.

Не знает про Robokassa/Stripe/ЮKassa — принимает уже проверенные данные
(подпись и сумма сверены снаружи, в роутере конкретного провайдера) и
отвечает за: идемпотентность по идентификатору платежа, начисление
партнёрской комиссии или обычной реферальной награды в SAVEPOINT, активацию
подписки. Специфичные для провайдера вещи (проверка подписи, сверка суммы,
формат идентификатора платежа) сюда не входят — это остаётся в роутере.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.models import User, Subscription, PaymentEvent, Partner
from backend.partners.commission import credit_commission
from backend.time_utils import utcnow

logger = logging.getLogger("astro.payments")

PERIOD_DAYS = {"monthly": 30, "annual": 365}
REFERRAL_REWARD_DAYS = 14

# Цена тарифа в рублях за месяц. Единственный источник этого числа на бэкенде:
# до 21.08.2026 тот же словарь был скопирован в admin/promo_router.py и
# admin/stats_router.py — три независимые копии одного числа расходятся рано
# или поздно (так уже случалось с charts_per_month и pdf_per_month, см.
# CLAUDE.md). Витрина — frontend/src/constants.js (TIER_PRICES), она обязана
# совпадать с этим словарём.
#
# premium здесь есть, хотя в чекаут не выпускается (Орион отключён в
# интерфейсе, yookassa_router отвечает на него 400): словарь нужен для расчёта
# MRR по уже выданным вручную премиумам и для промокодов в админке. Источником
# цены для показа пользователю он не является — фронт берёт цены из своего
# constants.js, а /pricing Орион не показывает.
TIER_PRICES_RUB = {"lite": 790, "pro": 2490, "premium": 7990}


class DuplicatePayment(Exception):
    """Платёж с этим payment_id уже обработан — не ошибка, вызывающая
    сторона должна подтвердить провайдеру приём (200 OK) и ничего не делать."""


class PaymentProcessingError(Exception):
    """Платёж не удалось обработать. `stage` — на каком шаге, для алертов."""

    def __init__(self, stage: str, message: str = ""):
        self.stage = stage
        super().__init__(message or stage)


class SubscriptionOwnerMissing(Exception):
    """Платёж проверен и записан, но активировать его НЕКОМУ: пользователя из
    metadata.user_id нет в БД.

    Отдельный тип, а не PaymentProcessingError, потому что ответ провайдеру
    противоположный (аудит 23.08.2026, находка 2.1). PaymentProcessingError
    означает «попробуй ещё раз» → 500 → ретрай. Здесь ретрай бессмыслен:
    причина постоянная — пользователь удалил аккаунт (`DELETE /api/v1/auth/me`
    доступен ему самому) между созданием платежа и вебхуком, либо строка
    пропала при восстановлении из бэкапа. Временный сбой БД сюда не попадает:
    он поднимает исключение из самого запроса и уходит в PaymentProcessingError,
    а `.first() is None` — это именно достоверное отсутствие.

    Запись о платеже к моменту возбуждения уже закоммичена (см.
    process_payment): деньги пришли, и след обязан остаться, даже когда
    активировать некому. Вызывающая сторона должна подтвердить приём (200) и
    сообщить владельцу — разбираться руками.
    """

    def __init__(self, user_id: str, payment_id: str = ""):
        self.user_id = user_id
        self.payment_id = payment_id
        super().__init__(f"user {user_id} not found for payment {payment_id or '?'}")


# ── Активация подписки ─────────────────────────────────────

def activate_subscription(user_id: str, tier: str, period: str, db: Session) -> None:
    """Активировать или продлить подписку. Всегда ровно одна строка на юзера.

    Срок считается от одной из двух точек (решение владельца 22.08.2026):

    • **Тот же тариф, подписка ещё действует** → срок СУММИРУЕТСЯ: отсчёт от
      текущей даты окончания, а не от сегодня. Заплативший дважды получает
      60 дней. Раньше второй платёж просто перезаписывал дату на «сегодня+30»,
      то есть оплаченный остаток первого молча пропадал.
    • **Другой тариф (апгрейд/даунгрейд) или подписка уже истекла** → отсчёт
      от сегодня, остаток сгорает.

    «Ещё действует» = `status == "active"` И дата окончания в будущем. Просто
    `status` недостаточно: `tasks.expire_subscriptions` ходит раз в сутки, и
    между истечением и его запуском строка остаётся `active` с датой в прошлом.
    Складывать с ней означало бы выдать меньше 30 дней за полный платёж.
    Та же проверка «дата в будущем, иначе сейчас» уже используется в
    `apply_referral_reward` ниже.

    Вторую строку не создаём никогда: `subscriptions.user_id` не уникален
    (наследство Stripe), а два одновременных платежа одного человека раньше
    оба не находили строку и оба вставляли свою. Дальше `.first()` без
    сортировки выбирал из них произвольную, а `expire_subscriptions`,
    наткнувшись на просроченную, сбрасывал тариф в free при живой второй —
    человек, заплативший дважды, терял доступ раньше срока. Уникальный индекс
    здесь не годится: он уронил бы второй платёж ошибкой БД вместо того, чтобы
    его обработать. Вместо этого строка User блокируется на время активации
    (`with_for_update`) — параллельный платёж дожидается и продлевает уже
    существующую подписку. Блокировка не может «не дать» платежу пройти, она
    только выстраивает их в очередь.
    """
    # Блокировка снимается вместе с транзакцией (db.commit() в конце функции).
    # SQLite (тесты) FOR UPDATE игнорирует — там всё и так последовательно.
    user = db.query(User).filter(User.id == user_id).with_for_update().first()
    if not user:
        # Раньше здесь был warning + return. Функция, обязанная либо
        # активировать, либо сообщить о невозможности, молча возвращала успех:
        # process_payment записывал «payment OK», вебхук отвечал 200, ЮKassa
        # прекращала доставку — а db.commit() ниже так и не выполнялся, и
        # сфлашенный PaymentEvent откатывался при закрытии сессии. Итог: деньги
        # списаны, подписки нет, следа нет (аудит 23.08.2026, находка 2.1).
        raise SubscriptionOwnerMissing(user_id)

    days = PERIOD_DAYS.get(period, 30)
    now = utcnow()

    # Порядок тот же, что в crm/router.py:427 и admin/stats_router.py: если
    # дубли всё же есть в базе (созданы до этого фикса), берём самую позднюю,
    # а не произвольную.
    sub = (
        db.query(Subscription)
        .filter(Subscription.user_id == user.id)
        .order_by(Subscription.current_period_end.desc().nullslast())
        .first()
    )

    still_active = bool(
        sub
        and sub.status == "active"
        and sub.current_period_end
        and sub.current_period_end > now
    )
    renewal = still_active and sub.tier == tier

    period_end = (sub.current_period_end if renewal else now) + timedelta(days=days)

    user.tier = tier

    if sub:
        sub.tier             = tier
        sub.status           = "active"
        sub.stripe_price_id  = f"{tier}_{period}"
        sub.current_period_end = period_end
    else:
        sub = Subscription(
            user_id=user.id,
            stripe_price_id=f"{tier}_{period}",
            status="active",
            tier=tier,
            current_period_end=period_end,
        )
        db.add(sub)

    db.commit()
    logger.info(
        "Activated: user=%s tier=%s period=%s until=%s (%s)",
        user_id, tier, period, period_end.date(),
        "продление, срок суммирован" if renewal else "отсчёт от сегодня",
    )

    # Приветственная цепочка писем по тарифу. Постановщик стоял в
    # payments/stripe_service.py и уехал вместе с ним в f3fc0a3 («удалить
    # Robokassa и Stripe как мёртвый код», 19.08.2026) — к ЮKassa цепочку
    # тогда не перепривязали, и с тех пор платящий человек не получал по
    # почте ничего: ни приветствия, ни даже подтверждения оплаты.
    #
    # ТОЛЬКО при renewal == False. Признак уже посчитан выше и означает
    # «живая подписка того же тарифа»: продливший Вегу на второй месяц
    # приветствие повторно не получит. Смена тарифа (lite -> pro) даёт
    # renewal == False намеренно — это новый тариф, и письмо про него
    # человек видит впервые.
    #
    # Ставится ПОСЛЕ db.commit(): подписка уже выдана, и что бы дальше ни
    # случилось с очередью, оплата не откатывается.
    if not renewal:
        try:
            from backend.tasks import (
                schedule_lite_emails,
                schedule_premium_emails,
                schedule_pro_emails,
            )
            _chain = {
                "lite": schedule_lite_emails,
                "pro": schedule_pro_emails,
                "premium": schedule_premium_emails,
            }.get(tier)
            if _chain is not None:
                _chain.delay(user.id)
        except Exception as exc:
            # Недоступный Redis/Celery не должен стоить человеку подписки:
            # деньги списаны, тариф выдан и закоммичен выше. Письмо —
            # приятное дополнение, а не часть оплаты.
            logger.warning(
                "Не удалось поставить цепочку писем: user=%s tier=%s: %s",
                user_id, tier, exc,
            )


def apply_referral_reward(referrer_user_id: str, db: Session) -> None:
    """«Пригласи друга — получи 2 недели Pro бесплатно»: продлить
    current_period_end уже активной ПЛАТНОЙ подписки реферера.

    Раньше это делалось через Stripe Coupon — требовал referrer.stripe_customer_id,
    награда молча не срабатывала для не-Stripe плательщиков. Теперь — прямое
    продление в своей БД. Free-рефереры бонус не получают: продлевать нечего,
    а выдавать pro без даты автоматического отзыва рискованно — у системы нет
    общего джоба, понижающего tier по истечении current_period_end (кроме
    отдельного cron для пилота, backend/pilot/cron.py), заводить такой ради
    этого бонуса не стали.

    Не для партнёров (Partner, backend/models.py) — та программа считает
    комиссию деньгами, а не днями подписки; вызывающая сторона (process_payment
    ниже) сама решает, что применить, эта функция ничего не проверяет про
    партнёрство.

    Ничего не коммитит — вызывается той же SAVEPOINT-веткой, что и
    credit_commission, коммит делает activate_subscription в конце общей
    транзакции с платежом.
    """
    referrer = db.query(User).filter(User.id == referrer_user_id).first()
    if not referrer:
        return

    sub = db.query(Subscription).filter(Subscription.user_id == referrer.id).first()
    if not sub or sub.status != "active" or referrer.tier == "free":
        logger.info("Referral reward skipped: referrer=%s has no active paid subscription", referrer_user_id)
        return

    base = sub.current_period_end if (sub.current_period_end and sub.current_period_end > utcnow()) else utcnow()
    sub.current_period_end = base + timedelta(days=REFERRAL_REWARD_DAYS)
    logger.info(
        "Referral reward applied: referrer=%s +%sd -> %s",
        referrer_user_id, REFERRAL_REWARD_DAYS, sub.current_period_end.date(),
    )


# ── Обработка проверенного платежа ─────────────────────────

def process_payment(
    db: Session,
    *,
    provider: str,
    payment_id: str,
    user_id: str,
    tier: str,
    period: str,
    amount: float,
) -> PaymentEvent:
    """Идемпотентно фиксирует платёж и активирует подписку.

    Вызывающая сторона (роутер конкретного провайдера) обязана сверить
    подпись и сумму ДО вызова этой функции — здесь предполагается, что
    (user_id, tier, period, amount) уже достоверны.

    Идемпотентность / anti-replay в БД: уникальный payment_id. Раньше ключ
    жил только в Redis, и при его недоступности код шёл дальше (fail-open) —
    тот же вебхук с валидной подписью продлевал подписку сколько угодно раз.

    Запись о платеже и сама активация — ОДНА транзакция. Если закоммитить
    payment_events отдельно и упасть на активации, повтор вебхука увидит
    существующий payment_id, провайдер получит подтверждение и уйдёт — деньги
    списаны, подписки нет, а ретраи провайдера конечны: почить нечем. Поэтому
    здесь flush (проверка уникальности без фиксации), затем активация, и
    только потом общий commit — его делает activate_subscription.

    Raises:
        DuplicatePayment: payment_id уже обработан — не ошибка, тот же ответ,
            что и на первый успешный вызов.
        PaymentProcessingError: сбой на шаге записи платежа или активации —
            стадия в `.stage` для алерта.
    """
    try:
        payment_event = PaymentEvent(
            provider=provider,
            inv_id=payment_id,
            user_id=user_id,
            tier=tier,
            period=period,
            amount=amount,
        )
        db.add(payment_event)
        db.flush()
    except IntegrityError:
        db.rollback()
        raise DuplicatePayment(payment_id) from None
    except Exception as exc:
        db.rollback()
        logger.exception("%s: payment_events insert failed, payment_id=%s", provider, payment_id)
        raise PaymentProcessingError("payment_events insert") from exc

    # Партнёрская комиссия и обычная реферальная награда не должны иметь
    # возможности сорвать реальный платёж. Голого try/except здесь
    # недостаточно: если код внутри падал уже после db.add()/запроса, сессия
    # SQLAlchemy оставалась в состоянии, требующем rollback, и следующий шаг
    # (activate_subscription, тот же db.commit()) валился следом за ней —
    # платёж откатывался целиком, хотя try/except формально стоял на месте.
    # begin_nested() — SAVEPOINT: при сбое откатывается только он, уже
    # сфлашенный payment_event остаётся цел.
    #
    # Комиссия и обычная награда взаимоисключающие для одного реферера —
    # партнёрская программа отдельная сущность, не смешивается с обычной
    # реферальной механикой: если реферер — активный партнёр, он получает
    # комиссию деньгами, а не 2 недели подписки в подарок.
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
        logger.exception("%s: referral reward/commission failed, payment_id=%s", provider, payment_id)

    try:
        activate_subscription(user_id=user_id, tier=tier, period=period, db=db)
    except SubscriptionOwnerMissing as exc:
        # ВАЖЕН ПОРЯДОК: эта ветка обязана стоять ВЫШЕ общего except —
        # тот делает rollback и потерял бы запись о платеже, ради сохранения
        # которой всё и затевалось.
        #
        # Коммитим: деньги пришли, активировать некому — след обязан остаться.
        # user.tier при этом не тронут, до него не дошли. Если сам commit
        # упадёт (вот это уже настоящий временный сбой), исключение уйдёт
        # наверх, вебхук ответит 500 и провайдер ретраит — и это правильно.
        exc.payment_id = payment_id
        db.commit()
        logger.error(
            "%s: платёж %s записан, но активировать некому — user %s не найден",
            provider, payment_id, user_id,
        )
        raise
    except Exception as exc:
        # Откатывает и активацию, и запись о платеже — ретрай провайдера
        # начнёт с чистого листа, а не упрётся в «уже обработано».
        db.rollback()
        logger.exception("%s: activate_subscription failed, payment_id=%s", provider, payment_id)
        raise PaymentProcessingError("activate_subscription") from exc

    logger.info("%s: payment OK, payment_id=%s user=%s tier=%s", provider, payment_id, user_id, tier)
    return payment_event
