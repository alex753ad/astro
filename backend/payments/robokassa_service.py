"""Robokassa payment service."""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from urllib.parse import urlencode

from backend.config import get_settings
from backend.models import User
from backend.email_service import TIER_NAMES

settings = get_settings()
logger = logging.getLogger("astro.robokassa")

# ── Цены в рублях ──────────────────────────────────────────
# Только разовая оплата за месяц — годовых периодов не предлагаем
# (самозанятая, разовый платёж на 1 месяц без автопродления).
TIER_PRICES: dict[tuple[str, str], float] = {
    ("lite",    "monthly"):   790.00,
    ("pro",     "monthly"):  2490.00,
    ("premium", "monthly"):  7990.00,
}

TIER_LABELS = TIER_NAMES


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
