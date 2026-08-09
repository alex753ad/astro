"""Robokassa payment service."""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import string
from datetime import timedelta
from backend.time_utils import utcnow
from urllib.parse import urlencode

from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.models import User, Subscription
from backend.email_service import TIER_NAMES

settings = get_settings()
logger = logging.getLogger("astro.robokassa")

# ── Цены в рублях ──────────────────────────────────────────
TIER_PRICES: dict[tuple[str, str], float] = {
    ("lite",    "monthly"):   790.00,
    ("lite",    "annual"):   7490.00,
    ("pro",     "monthly"):  1990.00,
    ("pro",     "annual"):  19900.00,
    ("premium", "monthly"):  7990.00,
    ("premium", "annual"):  79900.00,
}

TIER_LABELS = TIER_NAMES
PERIOD_DAYS = {"monthly": 30, "annual": 365}


# ── Подпись ────────────────────────────────────────────────

def _md5(s: str) -> str:
    # MD5 не выбор, а требование протокола Robokassa: подпись платёжного
    # шлюза считается им и только им, другой алгоритм не даст совпадения при
    # верификации на их стороне. usedforsecurity=False — эта MD5 не участвует
    # ни в чём криптографически значимом со стороны приложения (не хеш пароля,
    # не проверка целостности данных, которым мы доверяем) и на некоторых
    # сборках OpenSSL требуется, чтобы вызов не падал в FIPS-режиме.
    return hashlib.md5(s.encode("utf-8"), usedforsecurity=False).hexdigest().upper()  # nosec B324


def _shp_string(shp: dict) -> str:
    """Строка Shp_* параметров, отсортированная по ключу."""
    return ":".join(f"{k}={v}" for k, v in sorted(shp.items()))


def _sign_payment(out_sum: str, inv_id: int, shp: dict) -> str:
    """Подпись для формирования ссылки (Password1)."""
    parts = [settings.robokassa_merchant_login, out_sum, str(inv_id), settings.robokassa_password1]
    shp_str = _shp_string(shp)
    if shp_str:
        parts.append(shp_str)
    return _md5(":".join(parts))


def _sign_verify(out_sum: str, inv_id: str, shp: dict) -> str:
    """Подпись для верификации вебхука (Password2)."""
    parts = [out_sum, inv_id, settings.robokassa_password2]
    shp_str = _shp_string(shp)
    if shp_str:
        parts.append(shp_str)
    return _md5(":".join(parts))


# ── Создание платёжной ссылки ──────────────────────────────

def create_payment_url(user: User, tier: str, billing_period: str) -> str:
    price = TIER_PRICES.get((tier, billing_period))
    if not price:
        raise ValueError(f"Unknown tier/period: {tier}/{billing_period}")

    # secrets, а не random: номер счёта участвует в подписи и в ключе
    # идемпотентности, предсказуемый ГПСЧ здесь не нужен. Диапазон — ограничение
    # Robokassa на InvId (32-битное знаковое).
    inv_id = secrets.randbelow(2_000_000_000) + 1
    out_sum = f"{price:.2f}"

    shp = {
        "Shp_period":  billing_period,
        "Shp_tier":    tier,
        "Shp_user_id": str(user.id),
    }

    sig = _sign_payment(out_sum, inv_id, shp)
    label = TIER_LABELS.get(tier, tier)

    params = {
        "MerchantLogin":  settings.robokassa_merchant_login,
        "OutSum":         out_sum,
        "InvId":          inv_id,
        "Description":    f"Подписка Astrea {label} ({billing_period})",
        "SignatureValue": sig,
        "IsTest":         "1" if settings.robokassa_is_test else "0",
        "Culture":        "ru",
        **shp,
    }

    base = "https://auth.robokassa.ru/Merchant/Index.aspx"
    return f"{base}?{urlencode(params)}"


# ── Верификация вебхука ────────────────────────────────────

def verify_payment(form_data: dict) -> tuple[bool, str, str, str]:
    """
    Проверяет подпись вебхука Robokassa.
    Возвращает: (valid, user_id, tier, period)
    """
    out_sum  = form_data.get("OutSum", "")
    inv_id   = form_data.get("InvId", "")
    sig_got  = form_data.get("SignatureValue", "").upper()

    shp = {k: v for k, v in form_data.items() if k.startswith("Shp_")}
    sig_exp = _sign_verify(out_sum, inv_id, shp)

    # compare_digest, а не !=: обычное сравнение строк выходит на первом
    # несовпавшем байте и по времени ответа позволяет подбирать подпись побайтно.
    if not hmac.compare_digest(sig_got, sig_exp):
        logger.warning("Robokassa sig mismatch for InvId=%s", inv_id)
        return False, "", "", ""

    return (
        True,
        shp.get("Shp_user_id", ""),
        shp.get("Shp_tier", ""),
        shp.get("Shp_period", "monthly"),
    )


# ── Активация подписки ─────────────────────────────────────

def activate_subscription(user_id: str, tier: str, period: str, db: Session) -> None:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        logger.warning("activate_subscription: user %s not found", user_id)
        return

    days = PERIOD_DAYS.get(period, 30)
    period_end = utcnow() + timedelta(days=days)

    user.tier = tier

    sub = db.query(Subscription).filter(Subscription.user_id == user.id).first()
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
    logger.info("Activated: user=%s tier=%s period=%s until=%s", user_id, tier, period, period_end.date())


def _generate_referral_code(db) -> str:
    """Generate unique 8-char alphanumeric referral code."""
    from backend.models import User as _User
    chars = string.ascii_uppercase + string.digits
    for _ in range(10):
        code = "".join(secrets.choice(chars) for _ in range(8))
        if not db.query(_User).filter(_User.referral_code == code).first():
            return code
    raise RuntimeError("Failed to generate unique referral code")
