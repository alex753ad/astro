"""Подключение Sentry — одно на api, worker и beat.

Без `SENTRY_DSN` ничего не инициализируется и ничего не отправляется: SDK даже
не импортируется. До 24.09.2026 подключение жило только в `main.py`, то есть
падения в воркере и beat до Sentry не доезжали бы и с DSN.

⚠️ **Персональных данных в событиях быть не должно** — дат и мест рождения,
текстов чата, email. `send_default_pii=False` убирает только то, что SDK
собирает сам (IP, cookies), поэтому поверх него `scrub`:

* тело запроса и query string — удаляются ЦЕЛИКОМ, а не маскируются по списку
  ключей: в теле `/chart/calculate` лежат дата и место рождения, в теле чата —
  вопрос человека, и список «чувствительных ключей» рано или поздно отстанет
  от новой ручки;
* хлебные крошки — только HTTP, и у них срезается всё после `?`: запрос к
  Nominatim несёт место рождения в query. Крошки логов и Redis выброшены —
  в них попадают тексты и значения кэша;
* `user` не передаётся вовсе;
* email в текстах исключений и сообщений заменяется на `[email]` целиком. Не
  через `mask_emails_in_text`: та оставляет первую букву и домен (`o***@x.ru`),
  что для логов годится, а стороннему сервису отдавать нельзя. Полагаться на
  скраббер Sentry тоже нельзя: это настройка проекта, её могут выключить.

`include_local_variables=False` — секреты в чужих фреймах (кортеж Basic-auth
ЮKassa внутри httpx), см. прежний комментарий в main.py, перенесён ниже.

Версия — `GIT_SHA`, её зашивает в образ сборка (Dockerfile, `05-update.sh`).
"""
from __future__ import annotations

import os

from backend.log_utils import _EMAIL_RE

_initialized = False


def _redact_emails(text: str) -> str:
    return _EMAIL_RE.sub("[email]", text)


def _strip_query(url):
    return url.split("?", 1)[0] if isinstance(url, str) else url


def scrub(event, hint=None):
    event.pop("user", None)

    request = event.get("request")
    if isinstance(request, dict):
        for k in ("data", "query_string", "cookies", "env"):
            request.pop(k, None)
        # IP клиента приходит через nginx заголовками. SDK без PII их и сам
        # убирает, но это его деталь реализации, а не наша гарантия.
        headers = request.get("headers")
        if isinstance(headers, dict):
            request["headers"] = {
                k: v for k, v in headers.items()
                if k.lower() not in ("x-forwarded-for", "x-real-ip", "forwarded", "authorization", "cookie")
            }
        if "url" in request:
            request["url"] = _strip_query(request["url"])

    crumbs = (event.get("breadcrumbs") or {}).get("values") or []
    kept = []
    for c in crumbs:
        if c.get("category") not in ("http", "httplib"):
            continue
        data = dict(c.get("data") or {})
        data.pop("http.query", None)
        data.pop("http.fragment", None)
        if "url" in data:
            data["url"] = _strip_query(data["url"])
        kept.append({**c, "data": data, "message": _strip_query(c.get("message"))})
    if event.get("breadcrumbs"):
        event["breadcrumbs"]["values"] = kept

    for key in ("message", "logentry"):
        value = event.get(key)
        if isinstance(value, str):
            event[key] = _redact_emails(value)
        elif isinstance(value, dict):
            for f in ("message", "formatted"):
                if isinstance(value.get(f), str):
                    value[f] = _redact_emails(value[f])
            value.pop("params", None)

    extra = event.get("extra")
    if isinstance(extra, dict):
        event["extra"] = {k: (_redact_emails(v) if isinstance(v, str) else v) for k, v in extra.items()}

    for exc in (event.get("exception") or {}).get("values") or []:
        if isinstance(exc.get("value"), str):
            exc["value"] = _redact_emails(exc["value"])

    return event


def init_sentry(dsn: str, service: str) -> bool:
    """`service` — api | worker | beat, уходит тегом. Пустой DSN — ничего."""
    global _initialized
    if not dsn or _initialized:
        return False
    import logging

    import sentry_sdk
    from sentry_sdk.integrations.logging import LoggingIntegration

    sentry_sdk.init(
        dsn=dsn,
        environment="production",
        release=os.getenv("GIT_SHA") or None,
        traces_sample_rate=0.1,
        send_default_pii=False,
        max_request_body_size="never",
        # Не отправлять локальные переменные фреймов (по умолчанию SDK их
        # отправляет). Секреты попадают туда не из нашего кода, а из чужих
        # фреймов в трейсбеке: httpx получает Basic-auth как кортеж
        # (shop_id, secret_key) — при любом исключении внутри httpx этот кортеж
        # уезжает в Sentry в открытом виде, и before_send его не видит, потому
        # что маскирование работает по тексту сообщений, а не по vars.
        # Тот же механизм касается JWT_SECRET, пароля БД и ключа Resend.
        # Событие, уже ушедшее к стороннему сервису, назад не отзывается —
        # поэтому выключаем целиком, а не пытаемся вычищать по списку.
        include_local_variables=False,
        # Логи — не крошками (в них тексты), а только событиями уровня ERROR.
        integrations=[LoggingIntegration(level=None, event_level=logging.ERROR)],
        before_send=scrub,
        before_send_transaction=scrub,
    )
    sentry_sdk.set_tag("service", service)
    _initialized = True
    return True
