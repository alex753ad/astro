"""Мониторинг очереди Celery: обработчик падений + сторож незапуска.

До 31.08.2026 мониторинга у очереди не было никакого. Практическое следствие:
падение или незапуск `tasks.expire_subscriptions` означало, что платные тарифы
перестают заканчиваться, и узнать об этом было неоткуда — `result_expires=3600`
стирает результат через час, логи не переживают перезапуск контейнера.

Здесь проверяются оба контура:
  А. `task_failure` → уведомление в Telegram, с троттлом на имя задачи;
  Б. метка живости в Redis + сторож, живущий ВНЕ очереди.
"""

import os
from datetime import timedelta
from unittest.mock import AsyncMock, patch

import fakeredis
import fakeredis.aioredis
import pytest

from backend import beat_watchdog
from backend.time_utils import utcnow

SECRET = "internal-secret-for-tests-0123456789"  # gitleaks:allow — тестовая фикстура


@pytest.fixture
def queue_redis():
    """Один Redis на оба контура: sync-клиент воркера и async-клиент ручки.

    Задача пишет метку СИНХРОННЫМ клиентом (beat_watchdog._sync_redis — почему
    отдельным, объяснено там же), а сторож читает её АСИНХРОННЫМ, потому что
    живёт в FastAPI. В бою это один и тот же Redis, и тест обязан быть таким
    же: два разных фейка проверяли бы половину пути каждый и пропустили бы
    рассинхрон ключа между писателем и читателем.

    Общий autouse-фикстур `fake_redis` из conftest подменяет только
    async-клиент — здесь он перекрывается клиентом на общем сервере.
    """
    server = fakeredis.FakeServer()
    sync_client = fakeredis.FakeRedis(server=server, decode_responses=True)
    async_client = fakeredis.aioredis.FakeRedis(server=server, decode_responses=True)
    with patch.object(beat_watchdog, "_sync_redis", return_value=sync_client), \
            patch("backend.redis_client.get_redis", return_value=async_client):
        yield sync_client


@pytest.fixture
def with_secret():
    with patch.dict(os.environ, {"INTERNAL_SECRET": SECRET}):
        yield


def _headers():
    return {"X-Internal-Secret": SECRET}


def _seed_marker(sync_client, age_hours: float) -> None:
    ts = (utcnow() - timedelta(hours=age_hours)).isoformat()
    sync_client.set(beat_watchdog.marker_key(beat_watchdog.WATCHED_TASK), ts)


# ═══════════════════════════════════════════════════════════
# А. Обработчик падений
# ═══════════════════════════════════════════════════════════


class _FakeEinfo:
    traceback = "Traceback (most recent call last):\n  File 'x.py', line 1\nBoom"


class _FakeSender:
    name = "tasks.expire_subscriptions"


class TestFailureHandler:
    def test_notifies_on_task_exception(self, queue_redis):
        """Падение задачи → сообщение в Telegram с именем, id и трейсбеком."""
        from backend.celery_app import _on_task_failure

        sent = AsyncMock(return_value=True)
        with patch("backend.notifications.telegram.send_support_message", sent):
            _on_task_failure(
                sender=_FakeSender(),
                task_id="abc-123",
                exception=ValueError("боль"),
                einfo=_FakeEinfo(),
            )

        sent.assert_awaited_once()
        text = sent.await_args.args[0]
        assert "tasks.expire_subscriptions" in text
        assert "abc-123" in text
        assert "ValueError: боль" in text
        assert "Traceback" in text

    def test_throttled_within_window(self, queue_redis):
        """Второе падение той же задачи в том же окне молчит."""
        from backend.celery_app import _on_task_failure

        sent = AsyncMock(return_value=True)
        with patch("backend.notifications.telegram.send_support_message", sent):
            for _ in range(3):
                _on_task_failure(
                    sender=_FakeSender(),
                    task_id="abc",
                    exception=ValueError("боль"),
                    einfo=_FakeEinfo(),
                )

        assert sent.await_count == 1

    def test_throttle_is_per_task_name(self, queue_redis):
        """Разложившаяся задача не заглушает первое падение соседней.

        Это отличие от _notify_ip_reject, где ключ один на всё: там поток
        отказов однороден, здесь молчание про expire_subscriptions — ровно та
        потеря, ради которой мониторинг и писался.
        """
        from backend.celery_app import _on_task_failure

        class _Other:
            name = "tasks.send_weekly_digest_task"

        sent = AsyncMock(return_value=True)
        with patch("backend.notifications.telegram.send_support_message", sent):
            _on_task_failure(sender=_FakeSender(), task_id="a", exception=ValueError("1"), einfo=None)
            _on_task_failure(sender=_FakeSender(), task_id="b", exception=ValueError("2"), einfo=None)
            _on_task_failure(sender=_Other(), task_id="c", exception=ValueError("3"), einfo=None)

        assert sent.await_count == 2
        texts = [c.args[0] for c in sent.await_args_list]
        assert any("expire_subscriptions" in t for t in texts)
        assert any("weekly_digest" in t for t in texts)

    def test_telegram_failure_does_not_raise(self, queue_redis):
        """Недоступный Telegram не должен усугублять исходную ошибку задачи."""
        from backend.celery_app import _on_task_failure

        boom = AsyncMock(side_effect=RuntimeError("telegram down"))
        with patch("backend.notifications.telegram.send_support_message", boom):
            _on_task_failure(
                sender=_FakeSender(), task_id="x", exception=ValueError("боль"), einfo=None
            )
        # Дошли сюда — значит наружу ничего не полетело.

    def test_redis_failure_does_not_raise(self):
        """Недоступный Redis (нечем троттлить) — тоже молча."""
        from backend.celery_app import _on_task_failure

        with patch.object(beat_watchdog, "_sync_redis", side_effect=OSError("no redis")):
            _on_task_failure(
                sender=_FakeSender(), task_id="x", exception=ValueError("боль"), einfo=None
            )


# ═══════════════════════════════════════════════════════════
# Б. Метка живости
# ═══════════════════════════════════════════════════════════


class TestMarker:
    def test_written_after_successful_run(self, queue_redis, db, monkeypatch):
        """Успешный прогон expire_subscriptions оставляет метку."""
        from backend import tasks

        monkeypatch.setattr(tasks, "SessionLocal", lambda: db)
        tasks.expire_subscriptions()

        assert queue_redis.get(beat_watchdog.marker_key(beat_watchdog.WATCHED_TASK))

    def test_not_written_when_task_fails(self, queue_redis, monkeypatch):
        """Падение до конца работы метку не оставляет.

        Иначе сторож подтверждал бы прогон, которого не было, — то есть
        мониторинг врал бы именно в том случае, ради которого он существует.
        """
        from backend import tasks

        def _boom():
            raise RuntimeError("БД недоступна")

        monkeypatch.setattr(tasks, "SessionLocal", _boom)
        with pytest.raises(RuntimeError):
            tasks.expire_subscriptions()

        assert queue_redis.get(beat_watchdog.marker_key(beat_watchdog.WATCHED_TASK)) is None

    def test_redis_failure_does_not_break_task(self, db, monkeypatch):
        """Недоступный Redis не роняет задачу: работа уже закоммичена."""
        from backend import tasks

        monkeypatch.setattr(tasks, "SessionLocal", lambda: db)
        with patch.object(beat_watchdog, "_sync_redis", side_effect=OSError("no redis")):
            result = tasks.expire_subscriptions()
        assert result == {"expired": 0}


# ═══════════════════════════════════════════════════════════
# Б. Сторож
# ═══════════════════════════════════════════════════════════


class TestWatchdog:
    def test_silent_when_marker_fresh(self, client, with_secret, queue_redis):
        """Свежая метка — молчим."""
        _seed_marker(queue_redis, age_hours=2.5)

        sent = AsyncMock(return_value=True)
        with patch("backend.notifications.telegram.send_support_message", sent):
            resp = client.post("/api/v1/internal/beat-watchdog", headers=_headers())

        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        sent.assert_not_awaited()

    def test_alerts_when_marker_stale(self, client, with_secret, queue_redis):
        """Метка старше порога — сообщаем."""
        _seed_marker(queue_redis, age_hours=27)

        sent = AsyncMock(return_value=True)
        with patch("backend.notifications.telegram.send_support_message", sent):
            resp = client.post("/api/v1/internal/beat-watchdog", headers=_headers())

        assert resp.status_code == 200
        assert resp.json()["status"] == "stale"
        sent.assert_awaited_once()
        assert "expire_subscriptions" in sent.await_args.args[0]

    def test_alerts_when_marker_missing(self, client, with_secret, queue_redis):
        """Метки нет вовсе — тоже тревога, а не молчание."""
        sent = AsyncMock(return_value=True)
        with patch("backend.notifications.telegram.send_support_message", sent):
            resp = client.post("/api/v1/internal/beat-watchdog", headers=_headers())

        assert resp.status_code == 200
        assert resp.json()["status"] == "missing"
        sent.assert_awaited_once()

    def test_task_write_is_visible_to_watchdog(self, client, with_secret, queue_redis, db, monkeypatch):
        """Сквозной путь: задача записала метку — сторож её видит и молчит.

        Главное, что здесь ловится, — рассинхрон ключа между писателем
        (sync-клиент воркера) и читателем (async-клиент ручки).
        """
        from backend import tasks

        monkeypatch.setattr(tasks, "SessionLocal", lambda: db)
        tasks.expire_subscriptions()

        sent = AsyncMock(return_value=True)
        with patch("backend.notifications.telegram.send_support_message", sent):
            resp = client.post("/api/v1/internal/beat-watchdog", headers=_headers())

        assert resp.json()["status"] == "ok"
        sent.assert_not_awaited()

    def test_returns_200_even_when_alerting(self, client, with_secret, queue_redis):
        """200 значит «проверка выполнена», а не «всё хорошо».

        Не-2xx сделал бы systemd-юнит красным при исправном стороже; результат
        читается из поля status, его печатает 09-internal-cron.sh в журнал.
        """
        sent = AsyncMock(return_value=True)
        with patch("backend.notifications.telegram.send_support_message", sent):
            resp = client.post("/api/v1/internal/beat-watchdog", headers=_headers())
        assert resp.status_code == 200

    def test_threshold_matches_timer_schedule(self):
        """Порог и расписание таймера подобраны в паре — не расходиться.

        Задача в 05:00 UTC, сторож в 07:30 UTC. Здоровый возраст метки ~2.5 ч,
        при одном пропуске ~26.5 ч. Порог обязан лежать между ними.
        """
        assert 2.5 * 3600 < beat_watchdog.MAX_AGE_SEC < 26.5 * 3600
