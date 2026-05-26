"""Celery application instance."""

from celery import Celery
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
    result_expires=3600,        # результаты хранятся 1 час
    task_track_started=True,    # статус STARTED виден клиенту
    worker_prefetch_multiplier=1,
    task_acks_late=True,
)
