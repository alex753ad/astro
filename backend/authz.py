"""Object-level authorization helpers (BOLA/IDOR protection)."""
from __future__ import annotations

from typing import Optional

from fastapi import HTTPException, status

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
