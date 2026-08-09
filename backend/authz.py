"""Object-level authorization helpers (BOLA/IDOR protection)."""
from __future__ import annotations

import hmac
import os
from typing import Optional

from fastapi import Header, HTTPException, status

from backend.models import NatalChart, User


def assert_chart_access(chart: NatalChart, user: Optional[User]) -> None:
    """Разрешает доступ к карте только владельцу либо для анонимной карты.

    Анонимные карты (user_id is None) остаются доступны, чтобы не ломать
    сценарий «расчёт до регистрации». Карта, принадлежащая другому
    пользователю, отдаёт 404 (не 403 — чтобы не подтверждать существование id).
    """
    if chart.user_id is None:
        return
    if user is None or chart.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chart not found")


def require_internal_secret(x_internal_secret: str = Header(default="")) -> None:
    """Защита служебных (cron/internal) эндпоинтов — fail-closed.

    Раньше в каждом таком роутере стояло `if secret and x_internal_secret != secret`.
    Пустой INTERNAL_SECRET означал, что проверка пропускается целиком, и эндпоинты
    выдачи pilot-токенов и массовых рассылок оказывались полностью открытыми: защита
    держалась на наличии одной переменной окружения. Теперь отсутствие секрета — это
    503 (ошибка конфигурации), а не молчаливое разрешение.

    Сравнение через hmac.compare_digest: обычный `!=` на строках выходит на первом
    несовпавшем байте и по времени ответа позволяет подбирать секрет посимвольно.
    """
    secret = os.getenv("INTERNAL_SECRET", "")
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Internal endpoints are disabled: INTERNAL_SECRET is not configured",
        )
    if not hmac.compare_digest(x_internal_secret, secret):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
