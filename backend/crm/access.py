"""backend/crm/access.py — E9 read-only CRM для экс-пилотного астролога.

После истечения пилота астролог падает на free. Обычный free никогда не имел
CRM (403). Но экс-пилот (был premium в пилоте) должен видеть витрину CRM
в режиме read-only: списки, карты, алерты — видны; действия (создать/изменить/
удалить/бриф/портал/отчёт) закрыты с текстом-замком.

Различаем три режима:
  full     — активный premium (в т.ч. активный пилот): полный доступ.
  readonly — экс-пилот (pilot_started_at есть и 30 дней прошли): только чтение.
  none     — обычный free без пилота: доступа нет (как и было, 403).

Использование в роутерах:
  from backend.crm.access import crm_read, crm_write
  _read  = Depends(crm_read)    # на GET-эндпоинты
  _write = Depends(crm_write)   # на POST/PATCH/DELETE
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, status

from backend.models import User
from backend.auth.dependencies import get_current_user

PILOT_DAYS = int(os.getenv("PILOT_DAYS", "30"))


def _is_ex_pilot(user: User) -> bool:
    if not getattr(user, "pilot_started_at", None):
        return False
    end = user.pilot_started_at + timedelta(days=PILOT_DAYS)
    return datetime.utcnow() >= end


def _is_active_premium(user: User) -> bool:
    return (user.tier or "free") == "premium"


def access_mode(user: User) -> str:
    if _is_active_premium(user):
        return "full"
    if _is_ex_pilot(user):
        return "readonly"
    return "none"


async def crm_read(user: User = Depends(get_current_user)) -> User:
    """GET-доступ: premium ИЛИ экс-пилот (read-only). Иначе 403."""
    mode = access_mode(user)
    if mode in ("full", "readonly"):
        return user
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={"error": "tier_required", "required": "premium", "current": user.tier or "free"},
    )


async def crm_write(user: User = Depends(get_current_user)) -> User:
    """Мутации: только активный premium.

    Экс-пилот → 403 с кодом crm_readonly (фронт показывает замок с нужным текстом).
    Обычный free → обычный tier_required.
    """
    mode = access_mode(user)
    if mode == "full":
        return user
    if mode == "readonly":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "crm_readonly", "required": "premium", "current": user.tier or "free"},
        )
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={"error": "tier_required", "required": "premium", "current": user.tier or "free"},
    )
