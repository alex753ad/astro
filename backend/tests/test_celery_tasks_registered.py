"""Регрессия №1 (аудит от 09.08): celery не был объявлен зависимостью вовсе,
а backend/celery_app.py и backend/tasks.py существовали, но ни один процесс их
не запускал — .delay()/.apply_async() клали задачу в Redis, откуда её никто
не забирал. Рассылка клиентам из CRM отвечала успехом, ничего не отправляя;
POST /transits/async всегда истекал таймаутом.

Здесь — не полноценный прогон воркера (нужен настоящий Redis-брокер), а
дешёвая гарантия того, что: пакет celery доступен, приложение импортируется,
и каждый объект, на котором в коде реально вызывается .delay()/.apply_async(),
это настоящая зарегистрированная Celery-задача, а не что-то, что тихо
проглотит вызов (обычный Python-объект без .name Celery не заметит на
стороне клиента — задача просто не поедет в очередь).
"""

import pytest


class TestTasksRegistered:

    def test_celery_app_imports(self):
        from backend.celery_app import celery_app
        assert celery_app.main == "astro"

    @pytest.mark.parametrize("import_path", [
        # payments/common.py: приветствие после оплаты
        "backend.tasks.send_purchase_welcome_task",
        # onboarding_router.py: /lunar-returns
        "backend.tasks.check_lunar_returns",
        # crm/dashboard_router.py:216, tasks.py:850 (send_broadcast_auto_task)
        "backend.tasks.send_client_broadcast_task",
        # celery_app.py: beat_schedule
        "backend.tasks.send_lifecycle_emails",
        "backend.tasks.send_weekly_digest_task",
        "backend.tasks.send_broadcast_auto_task",
        "backend.tasks.expire_subscriptions",
    ])
    def test_dispatched_object_is_a_registered_task(self, import_path):
        import importlib
        module_path, attr = import_path.rsplit(".", 1)
        module = importlib.import_module(module_path)
        obj = getattr(module, attr)

        assert hasattr(obj, "delay"), f"{import_path} не Celery-задача — .delay() не пошлёт ничего"
        assert hasattr(obj, "name") and obj.name, f"{import_path} без .name — Celery не сможет её маршрутизировать"

        from backend.celery_app import celery_app
        assert obj.name in celery_app.tasks, (
            f"{import_path} (name={obj.name!r}) не найдена в celery_app.tasks — "
            f"воркер получит задачу с этим именем и не будет знать, что выполнять"
        )

    def test_retired_email_tasks_stay_registered(self):
        """Под этими именами в Redis ещё лежат сообщения с ETA до 30 суток:
        снятое имя уронило бы воркер на незарегистрированной задаче. Заглушки
        снимаются после 24.10.2026 (TASKS.md) — вместе с этим тестом."""
        from backend.celery_app import celery_app
        from backend.tasks import _RETIRED_TASK_NAMES

        assert len(_RETIRED_TASK_NAMES) == 12
        for name in _RETIRED_TASK_NAMES:
            assert name in celery_app.tasks, name
            assert celery_app.tasks[name].run(1) is None

    def test_beat_schedule_points_to_registered_tasks(self):
        from backend.celery_app import celery_app
        import backend.tasks  # noqa: F401 — регистрирует @celery_app.task(...)

        registered = set(celery_app.tasks.keys())
        for entry_name, entry in celery_app.conf.beat_schedule.items():
            assert entry["task"] in registered, (
                f"beat_schedule['{entry_name}'] ссылается на незарегистрированную задачу "
                f"{entry['task']!r} — опечатка в имени останется незамеченной, пока никто "
                f"не полезет смотреть логи beat"
            )
