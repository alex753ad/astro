"""Celery application instance."""

import logging

from celery import Celery
from celery.schedules import crontab
from celery.signals import task_failure

from backend.config import get_settings

logger = logging.getLogger("astro.celery")

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
        # Ежемесячная рассылка клиентам — ежедневно 09:10 МСК; задача сама шлёт только 1-го числа
        "send-client-broadcast-monthly": {
            "task": "tasks.send_broadcast_auto",
            "schedule": crontab(hour=6, minute=10),
        },
        # Истёкшие подписки → free. 08:00 МСК: намеренно не рядом с ночным
        # pg_dump (03:30, systemd-таймер, deploy/opt-astro/07-backup-cron.sh) —
        # массовый UPDATE во время дампа не ломает его, но удлиняет обоих.
        "expire-subscriptions-daily": {
            "task": "tasks.expire_subscriptions",
            "schedule": crontab(hour=5, minute=0),
        },
    },
    beat_timezone="UTC",
)


# ═══════════════════════════════════════════════════════════
# Уведомления о падениях задач
# ═══════════════════════════════════════════════════════════
#
# До 31.08.2026 у очереди не было мониторинга вообще: ни Flower, ни Sentry в
# воркере, ни обработчиков сигналов. `result_expires=3600` стирает результат
# через час, логи не переживают перезапуск контейнера — упавшая задача не
# оставляла следов нигде. Практическое следствие: если падала
# `expire_subscriptions`, платные тарифы переставали заканчиваться, и узнать
# об этом было неоткуда.
#
# Сообщаем ТОЛЬКО о падениях. Ежедневный отчёт «всё хорошо» читать перестают
# через неделю, после чего он не отличается от отсутствия мониторинга.

_FAILURE_NOTIFY_KEY = "astro:celery:failure_notified:"
_FAILURE_COUNT_KEY = "astro:celery:failure_count:"
_FAILURE_WINDOW_SEC = 3600

# Сколько первых строк трейсбека класть в сообщение. Целиком он не влезает в
# лимит Telegram (4096), а send_support_message молча обрежет хвост.
_TRACEBACK_LINES = 12
_TRACEBACK_MAX_CHARS = 1200


@task_failure.connect
def _on_task_failure(sender=None, task_id=None, exception=None, einfo=None, **_kwargs):
    """Сообщить владельцу об упавшей задаче — не чаще раза в час на задачу.

    ⚠️ Обработчик обязан быть неспособен уронить задачу. Защита двухслойная:

    1. **Celery уже ловит исключения получателей сигнала.**
       `celery.utils.dispatch.Signal.send` оборачивает каждый вызов в
       `try/except Exception`, пишет `logger.exception` и складывает исключение
       в список ответов — наружу оно не идёт (проверено по исходнику
       установленной версии; в Celery `send` и `send_robust` делают одно и то
       же, в отличие от Django).
    2. **Свой сплошной `try/except` поверх — всё равно.** Полагаться на п.1
       нельзя по двум причинам. Это деталь реализации зависимости, которая
       может измениться при обновлении. И главное: перехват Celery пишет
       ПОЛНЫЙ трейсбек обработчика через `logger.exception` — он ляжет в лог
       вплотную к настоящему падению задачи, и читающий увидит два трейсбека
       без понимания, какой из них причина. Это ровно то маскирование, которого
       быть не должно: свой перехват оставляет одну строку WARNING.

    Сверх того, `task_failure` срабатывает уже ПОСЛЕ того, как падение задачи
    зафиксировано, — повлиять на её исход обработчик не может в принципе.

    Недоступность Redis (нечем троттлить) и недоступность Telegram обе ведут к
    одному: сообщение не уходит, в лог пишется WARNING, задача не трогается.
    """
    try:
        _notify_task_failure(sender, task_id, exception, einfo)
    except Exception as exc:  # noqa: BLE001 — именно сплошной, см. докстринг
        logger.warning("celery failure notifier failed: %s", exc)


def _task_name(sender) -> str:
    return getattr(sender, "name", None) or str(sender)


def _notify_task_failure(sender, task_id, exception, einfo) -> None:
    import asyncio

    from backend.beat_watchdog import _sync_redis
    from backend.notifications.telegram import send_support_message

    name = _task_name(sender)

    # Троттл — по ИМЕНИ задачи, а не один на всю очередь (в отличие от
    # _notify_ip_reject, где поток отказов однороден). Разложившаяся задача,
    # падающая каждую минуту, не должна заглушать первое падение соседней:
    # молчание про expire_subscriptions — ровно та потеря, ради которой всё
    # это писалось.
    redis = _sync_redis()
    failures = redis.incr(_FAILURE_COUNT_KEY + name)
    if failures == 1:
        redis.expire(_FAILURE_COUNT_KEY + name, _FAILURE_WINDOW_SEC)
    # SET NX: окно занимает ровно один процесс, даже если воркеры уронили
    # задачу одновременно.
    claimed = redis.set(
        _FAILURE_NOTIFY_KEY + name, "1", ex=_FAILURE_WINDOW_SEC, nx=True
    )
    if not claimed:
        return
    # Следующее окно считает с нуля — в сообщении число за период, а не с
    # начала времён.
    redis.delete(_FAILURE_COUNT_KEY + name)

    text = (
        "🔴 Celery: задача упала\n"
        f"Задача: {name}\n"
        f"ID: {task_id}\n"
        f"Ошибка: {type(exception).__name__}: {exception}\n"
        f"Падений за последний час: {failures}\n"
        f"{_traceback_head(einfo)}"
    )
    asyncio.run(send_support_message(text))


def _traceback_head(einfo) -> str:
    tb = getattr(einfo, "traceback", None)
    if not tb:
        return ""
    head = "\n".join(str(tb).splitlines()[:_TRACEBACK_LINES])[:_TRACEBACK_MAX_CHARS]
    return f"\nТрейсбек (начало):\n{head}"
