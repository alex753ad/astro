"""Chart selection helpers shared across the web service and Celery tasks.

Deliberately free of any backend.tasks/celery imports — this module must be
safe to import at module level from the main FastAPI app (celery isn't
installed there, only in the separate worker service).
"""
from __future__ import annotations

from backend.models import NatalChart


def get_primary_chart(db, user) -> NatalChart | None:
    """Return user's primary chart.

    Priority:
      1. user.primary_chart_id — явно выбранная главная карта
      2. последняя сохранённая карта (fallback для пользователей без pin)
    """
    if user.primary_chart_id:
        chart = (
            db.query(NatalChart)
            .filter(
                NatalChart.id == user.primary_chart_id,
                NatalChart.user_id == user.id,
            )
            .first()
        )
        if chart:
            return chart
    # fallback
    return (
        db.query(NatalChart)
        .filter(NatalChart.user_id == user.id)
        .order_by(NatalChart.created_at.desc())
        .first()
    )
