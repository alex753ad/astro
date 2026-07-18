"""Общий SlowAPI-лимитер и определение реального IP клиента.

За обратным прокси `request.client.host` — это адрес прокси, а не клиента:
без доверенного списка все запросы попадали в один счётчик, то есть лимит был
общим на всё приложение. Доверять X-Forwarded-For целиком тоже нельзя — клиент
шлёт свой заголовок сам, и левые сегменты подделываются.

Правило: заголовку верим, только если непосредственный peer перечислен в
TRUSTED_PROXY_IPS. Тогда идём по X-Forwarded-For справа налево, пропуская
доверенные прокси, и берём первый недоверенный адрес — его приписал ближайший
доверенный прокси, подделать нельзя. Если список пуст, заголовок игнорируется
полностью (fail-closed) и ключом остаётся peer.

Счётчики живут в Redis: при нескольких воркерах in-memory storage дал бы
каждому свой лимит, то есть фактический порог умножался бы на число воркеров.
"""
from __future__ import annotations

import ipaddress
import logging

from fastapi import Request
from slowapi import Limiter

from backend.config import get_settings

logger = logging.getLogger("astro.limiter")

settings = get_settings()


def _parse_networks(raw: str) -> list:
    """Разбирает список доверенных прокси: IP или CIDR через запятую."""
    networks = []
    for item in (raw or "").split(","):
        item = item.strip()
        if not item:
            continue
        try:
            networks.append(ipaddress.ip_network(item, strict=False))
        except ValueError:
            logger.error("Invalid entry in TRUSTED_PROXY_IPS, ignored: %r", item)
    return networks


TRUSTED_PROXIES = _parse_networks(settings.trusted_proxy_ips)


def _is_trusted(addr: str) -> bool:
    if not TRUSTED_PROXIES:
        return False
    try:
        ip = ipaddress.ip_address(addr.strip())
    except ValueError:
        return False
    return any(ip in net for net in TRUSTED_PROXIES)


def client_ip(request: Request) -> str:
    """Реальный IP клиента с учётом доверенных прокси."""
    peer = request.client.host if request.client else "unknown"

    if not _is_trusted(peer):
        # Прямое подключение либо недоверенный прокси — заголовкам не верим.
        return peer

    forwarded = request.headers.get("X-Forwarded-For", "")
    for hop in reversed([h.strip() for h in forwarded.split(",") if h.strip()]):
        if not _is_trusted(hop):
            return hop

    # Все сегменты доверенные (или заголовка нет) — клиент и есть прокси.
    return peer


limiter = Limiter(
    key_func=client_ip,
    storage_uri=settings.rate_limit_storage_uri or settings.redis_url,
)
