"""Сторож расписания Celery Beat: метка живости + проверка незапуска.

Зачем отдельный модуль, а не строчка в tasks.py: ключ метки и порог возраста
нужны в ДВУХ местах — задача метку пишет, сторож её читает. Разнесённые по
разным файлам, два числа, обязанные совпадать, рано или поздно расходятся
(так уже было с `charts_per_month` и `profiles_limit`, см. CLAUDE.md).
Здесь они объявлены по одному разу.

⚠️ **Главное решение модуля: сторож живёт в контейнере `api`, а НЕ в Celery.**
Задача-сторож внутри той очереди, за которой следит, встанет вместе с ней и
промолчит ровно в тот момент, когда она нужна. Поэтому проверка — обычная
HTTP-ручка `POST /api/v1/internal/beat-watchdog`, а дёргает её systemd-таймер
на хосте (`deploy/opt-astro/systemd/astro-beat-watchdog.*`) тем же скриптом
`09-internal-cron.sh`, что и остальные служебные ручки. Ни воркер, ни beat,
ни брокер в этом пути не участвуют.

Следствие: единственная общая точка отказа у задачи и сторожа — сам Redis.
Она обработана явно: недоступный Redis трактуется как «проверить не смогли»
и тоже уводит в уведомление (при мёртвом Redis очередь всё равно не работает
— брокер тот же самый).
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from backend.authz import require_internal_secret
from backend.time_utils import utcnow

logger = logging.getLogger("astro.beat_watchdog")

# Секрет проверяется на уровне роутера — см. backend/authz.require_internal_secret.
router = APIRouter(
    prefix="/api/v1/internal",
    tags=["internal"],
    dependencies=[Depends(require_internal_secret)],
)

_MARKER_PREFIX = "astro:beat:last_success:"

# Пока следим за одной задачей. Остальные три расписания (lunar-returns,
# weekly-digest, broadcast) намеренно не подключены: сначала смотрим, как
# механизм ведёт себя на одной — решение владельца 31.08.2026. С 29.09.2026
# (решение владельца) сторож проверяет ещё и доставку утреннего сообщения
# самопроверки — `_check_morning` ниже; это отдельная отметка, а не вторая
# задача в WATCHED_TASK.
WATCHED_TASK = "tasks.expire_subscriptions"

# 26 часов, а не 24. Задача идёт в 05:00 UTC, сторож — в 07:30 UTC (см. юниты
# в deploy/opt-astro/systemd/). На здоровом сервере метке в этот момент ~2.5 ч.
# Если прогон пропущен ровно один раз, метке будет ~26.5 ч — то есть порог
# отделяет «пропустили один запуск» от «всё в порядке» с запасом в обе
# стороны, и при этом не срабатывает от джиттера RandomizedDelaySec.
MAX_AGE_SEC = 26 * 3600


def marker_key(task_name: str) -> str:
    return f"{_MARKER_PREFIX}{task_name}"


# ── Запись метки (sync, из Celery-задачи) ───────────────────────────────────

_sync_client = None


def _sync_redis():
    """Отдельный СИНХРОННЫЙ клиент Redis для воркера.

    Не переиспользуем `backend.redis_client.get_redis()`: тот async и кэширует
    клиент в module-global. Celery-задачи синхронные и зовут async-код через
    `asyncio.run`, а это каждый раз НОВЫЙ event loop — закэшированный
    aioredis-клиент остался бы привязан к уже закрытому циклу и упал бы на
    втором вызове. Синхронный клиент этой проблемы не имеет.
    """
    global _sync_client
    if _sync_client is None:
        import redis

        from backend.config import get_settings

        # Оба таймаута обязательны и оба по 2 с. Без socket_connect_timeout
        # мёртвый Redis вешает вызывающего на системном таймауте TCP; без
        # socket_timeout — на полуоткрытом соединении, где connect прошёл, а
        # ответа на команду нет. Замер на живом коде: недоступный Redis даёт
        # исключение через 2.03 с, ретраев нет. Это цена, которую платит
        # Celery-задача ПОСЛЕ того, как сделала полезную работу, — приемлемо;
        # неограниченное ожидание здесь означало бы висящий воркер.
        _sync_client = redis.from_url(
            get_settings().redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
    return _sync_client


def mark_success(task_name: str) -> None:
    """Отметить успешный прогон задачи. Вызывать ПОСЛЕ полезной работы.

    Метка живёт без TTL намеренно. С TTL «метки нет» означало бы сразу два
    разных состояния — «протухла» и «никогда не писалась», — и сторож не смог
    бы их различить. Без TTL отсутствие метки всегда значит одно: подтверждения
    прогона у нас нет, надо будить владельца.

    Ошибка записи НЕ поднимается наверх: полезная работа задачи к этому моменту
    уже закоммичена, и ронять задачу из-за недоступного Redis значило бы
    превратить сбой мониторинга в сбой того, за чем он следит. Худшее
    последствие — сторож не увидит свежей метки и пришлёт ложную тревогу; это
    честнее, чем молча потерять понижение тарифов.
    """
    try:
        _sync_redis().set(marker_key(task_name), utcnow().isoformat())
    except Exception as exc:
        logger.warning(
            "beat watchdog: не удалось записать метку успеха для %s: %s", task_name, exc
        )


# ── Проверка (async, из ручки в контейнере api) ─────────────────────────────


async def _read_marker_age(task_name: str) -> tuple[str, float | None, str | None]:
    """Возвращает (state, age_sec, raw) — state: ok | missing | unreadable."""
    from datetime import datetime

    from backend import redis_client

    raw = await redis_client.get_redis().get(marker_key(task_name))
    if not raw:
        return "missing", None, None
    try:
        ts = datetime.fromisoformat(raw)
    except ValueError:
        return "unreadable", None, raw
    age = (utcnow() - ts).total_seconds()
    return "ok", age, raw


@router.post("/beat-watchdog")
async def beat_watchdog() -> dict:
    """Две проверки: `WATCHED_TASK` отработала не позже `MAX_AGE_SEC` назад, и
    утреннее сообщение самопроверки сегодня дошло в канал (`_check_morning`).

    Отвечает 200 в любом исходе, включая тревогу: 200 здесь значит «проверка
    выполнена», а не «всё хорошо». Не-2xx сделал бы systemd-юнит красным при
    исправном сторожe и живом сервере, а само уведомление всё равно уходит в
    Telegram — то есть единственным эффектом был бы застрявший failed-юнит.
    Результат проверки — в поле `status` ответа, его печатает
    `09-internal-cron.sh` в журнал юнита.

    Троттла нет, в отличие от `_notify_ip_reject` и обработчика падений: сторож
    запускается раз в сутки, значит и сообщений будет максимум по одному на
    проверку в сутки.
    Повтор здесь желателен — пока очередь не починили, напоминать надо каждый
    день, иначе единственное сообщение утонет в переписке.
    """
    from backend.notifications.telegram import send_support_message

    result = await _check_expire(send_support_message)
    result["morning"] = await _check_morning(send_support_message)
    return result


async def _check_expire(send_support_message) -> dict:
    try:
        state, age, _raw = await _read_marker_age(WATCHED_TASK)
    except Exception as exc:
        # Redis не ответил. Брокер Celery — тот же Redis, значит очередь сейчас
        # тоже не работает: это не «проверить не смогли», это отказ по существу.
        logger.error("beat watchdog: Redis недоступен: %s", exc)
        await _alert(
            send_support_message,
            f"Redis не отвечает — проверить расписание невозможно.\n"
            f"Брокер Celery это тот же Redis, значит очередь сейчас стоит: "
            f"истёкшие подписки не понижаются.\nОшибка: {exc}",
        )
        return {"status": "redis_unavailable", "task": WATCHED_TASK}

    if state == "ok" and age is not None and age <= MAX_AGE_SEC:
        return {"status": "ok", "task": WATCHED_TASK, "age_sec": int(age)}

    if state == "missing":
        detail = (
            "Метки успешного прогона нет вообще.\n"
            "Либо задача ни разу не отработала после включения сторожа, "
            "либо Redis потерял данные."
        )
    elif state == "unreadable":
        detail = "Метка есть, но её не разобрать как дату — записана чем-то посторонним."
    else:
        hours = (age or 0) / 3600
        detail = (
            f"Последний успешный прогон был {hours:.1f} ч назад "
            f"(порог — {MAX_AGE_SEC // 3600} ч)."
        )

    await _alert(
        send_support_message,
        f"{detail}\n\n"
        f"Задача: {WATCHED_TASK} (по расписанию ежедневно в 05:00 UTC).\n"
        "Пока она не идёт, истёкшие платные подписки НЕ понижаются до free — "
        "оплаченный месяц не заканчивается.\n\n"
        "Проверить: docker compose ps beat worker; "
        "docker compose logs --tail=100 beat",
    )
    return {
        "status": "stale" if state == "ok" else state,
        "task": WATCHED_TASK,
        "age_sec": int(age) if age is not None else None,
    }


# ── Утреннее сообщение самопроверки (с 29.09.2026) ──────────────────────────
#
# `selfcheck.run_daily` в 07:30 МСК шлёт в канал одно сообщение каждое утро —
# чтобы тишина отличалась от упавшей самопроверки. Но если прогон не случился
# вовсе (beat или worker стоят), то нет ни сообщения, ни ERROR в логе, и тишина
# снова ничем не отличается. Поэтому доставку подтверждает отметка в Redis, а
# проверяет её этот сторож: он живёт вне очереди (см. шапку модуля) и идёт в
# 07:30 UTC = 10:30 МСК, через три часа после самопроверки.
#
# Отметка — дата по Москве, а не время: «сегодня дошло» или нет. Без TTL, по
# той же причине, что метка задачи выше.

MORNING_KEY = "astro:selfcheck:morning_sent"
MORNING_TZ = "Europe/Moscow"


def morning_today(now=None) -> str:
    """Сегодняшняя дата по Москве — значение отметки. `now` — наивный UTC."""
    from datetime import timezone
    from zoneinfo import ZoneInfo

    now = now or utcnow()
    return now.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(MORNING_TZ)).date().isoformat()


def mark_morning_sent(redis) -> None:
    """Отметить, что Telegram принял утреннее сообщение. Зовёт run_daily
    синхронным клиентом воркера. Ошибка не поднимается: худшее — ложная
    тревога от сторожа, а не упавшая самопроверка."""
    try:
        redis.set(MORNING_KEY, morning_today())
    except Exception as exc:
        logger.warning("beat watchdog: отметка утреннего сообщения не записана: %s", exc)


async def _check_morning(send) -> str:
    """ok | missing | redis_unavailable.

    ⚠️ Тревога уходит ДВУМЯ путями: в канал и ERROR в лог (→ Sentry). Один из
    двух отказов, который тут ловится, — сам канал (Telegram не принял
    утреннее сообщение, как было с 02.09 по 27.09 из-за не того бота), и
    тогда тревога в тот же канал тоже не дойдёт. Sentry — второй путь.

    Недоступный Redis здесь молчит: о нём уже сказала проверка задачи выше,
    второе сообщение о той же причине ничего не добавит.
    """
    from backend import redis_client

    today = morning_today()
    try:
        raw = await redis_client.get_redis().get(MORNING_KEY)
    except Exception as exc:
        logger.warning("beat watchdog: отметку утреннего сообщения не прочитать: %s", exc)
        return "redis_unavailable"
    if raw == today:
        return "ok"
    logger.error(
        "beat watchdog: утреннее сообщение самопроверки за %s в канал не дошло (последняя отметка: %s)",
        today, raw or "нет",
    )
    await _alert(
        send,
        f"утреннее сообщение самопроверки (07:30 МСК) за {today} в канал не дошло.\n"
        f"Последняя доставка: {raw or 'не отмечена ни разу'}.\n\n"
        "Либо самопроверка не запускалась (beat или worker стоят), либо Telegram "
        "не принял сообщение — тогда и это может не дойти, дубль ушёл в Sentry.\n\n"
        "Проверить: docker compose ps beat worker; "
        "docker compose logs --tail=200 worker | grep selfcheck",
    )
    return "missing"


async def _alert(sender, body: str) -> None:
    """Отправить тревогу, проглотив любую ошибку отправки.

    Сторож не должен падать из-за недоступного Telegram: его ненулевой код
    сделал бы systemd-юнит красным и увёл разбор в ложную сторону — «сломался
    мониторинг» вместо «стоит очередь».
    """
    text = f"⏰ Расписание Celery: {body}"
    try:
        await sender(text)
    except Exception as exc:
        logger.warning("beat watchdog: не удалось отправить уведомление: %s", exc)
