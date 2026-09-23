"""Служебные ручки рассылок: еженедельный дайджест и лунные возвращения.
Protected by X-Internal-Secret header.
"""
from __future__ import annotations
import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.authz import require_internal_secret
from backend.database import get_db

logger = logging.getLogger("astro.onboarding")

# Секрет проверяется на уровне роутера: все маршруты здесь служебные (cron), и
# при добавлении нового он не окажется случайно открытым.
router = APIRouter(
    prefix="/api/v1/internal",
    tags=["internal"],
    dependencies=[Depends(require_internal_secret)],
)

# Письма day2/day7 жили здесь ручкой POST /onboarding-emails (systemd-таймер,
# от даты регистрации) параллельно с цепочкой Celery от первой карты — два
# пути одного письма. С 23.09.2026 путь один: Beat + журнал,
# backend/lifecycle_emails.py. Ручку не возвращать.


async def run_weekly_digest(db: Session) -> dict:
    """Основная логика — переиспользуется HTTP-эндпоинтом ниже и внутренним
    планировщиком в main.py (см. lifespan). Отправляет дайджест пользователям,
    у которых сегодня настроен день получения (digest_day_of_week == today.weekday()).
    """
    from datetime import date as date_type
    from backend.models import User
    from backend.email_service import send_weekly_digest

    today_weekday = date_type.today().weekday()  # 0=пн, 6=вс

    pro_users = db.query(User).filter(
        User.tier.in_(["pro", "premium"]),
        User.digest_day_of_week == today_weekday,
    ).all()
    sent = 0
    for user in pro_users:
        try:
            ok = await send_weekly_digest(user, db)
            if ok:
                sent += 1
        except Exception as e:
            logger.warning("Weekly digest failed for %s: %s", user.email, e)

    return {"sent": sent, "weekday": today_weekday}


@router.post("/weekly-digest")
async def send_weekly_digests(
    db: Session = Depends(get_db),
):
    """Railway Cron: ежедневно 09:00 МСК."""
    return await run_weekly_digest(db)


@router.post("/lunar-returns")
async def trigger_lunar_returns(
    db: Session = Depends(get_db),
):
    """Railway Cron: ежедневно 09:00 МСК.
    Запускает Celery-задачу проверки лунных возвращений.
    """
    try:
        from backend.tasks import check_lunar_returns
        task = check_lunar_returns.delay()
        return {"status": "queued", "task_id": task.id}
    except Exception as e:
        logger.warning("lunar-returns trigger failed: %s", e)
        # Fallback: выполнить синхронно
        from backend.tasks import check_lunar_returns
        result = check_lunar_returns()
        return {"status": "done", **result}
