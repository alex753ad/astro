"""Реферальные коды пользователей. Провайдер-независимо — не завязано ни на
Robokassa, ни на будущую ЮKassa, используется при регистрации и в профиле.
"""

from __future__ import annotations

import secrets
import string


def generate_referral_code(db) -> str:
    """Generate unique 8-char alphanumeric referral code."""
    from backend.models import User as _User
    chars = string.ascii_uppercase + string.digits
    for _ in range(10):
        code = "".join(secrets.choice(chars) for _ in range(8))
        if not db.query(_User).filter(_User.referral_code == code).first():
            return code
    raise RuntimeError("Failed to generate unique referral code")
