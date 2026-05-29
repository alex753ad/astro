"""Celery application instance."""

from celery import Celery
from celery.schedules import crontab
from backend.config import get_settings

settings = get_settings()

celery_app = Celery(
    "astro",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["backend.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    result_expires=3600,
    task_track_started=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,

    # ── Celery Beat — периодические задачи ──
    beat_schedule={
        # Лунные возвращения — каждый день в 09:00 МСК (06:00 UTC)
        "check-lunar-returns-daily": {
            "task": "tasks.check_lunar_returns",
            "schedule": crontab(hour=6, minute=0),
        },
        # Weekly digest — каждый день в 09:00 МСК (фильтрует по digest_day_of_week сам)
        "send-weekly-digest-daily": {
            "task": "tasks.send_weekly_digest_task",
            "schedule": crontab(hour=6, minute=5),
        },
    },
    beat_timezone="UTC",
)

