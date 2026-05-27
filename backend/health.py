"""Health check utilities for services."""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import time
from typing import Literal

import httpx
from prometheus_client import Counter, Histogram
from sqlalchemy import text

from backend.config import get_settings
from backend.database import engine

logger = logging.getLogger("astro.health")

HealthStatus = Literal["ok", "degraded", "down"]

# Prometheus metrics
health_check_total = Counter(
    "health_check_total",
    "Total number of health checks",
    ["service", "status"]
)

health_check_duration_seconds = Histogram(
    "health_check_duration_seconds",
    "Health check duration in seconds",
    ["service"],
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0]
)

# Отдельные гистограммы для каждого сервиса с более детальными buckets
health_check_latency_openai = Histogram(
    "health_check_latency_openai_seconds",
    "OpenAI health check latency",
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 10.0]
)

health_check_latency_deepseek = Histogram(
    "health_check_latency_deepseek_seconds",
    "DeepSeek health check latency",
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 10.0]
)

health_check_latency_redis = Histogram(
    "health_check_latency_redis_seconds",
    "Redis health check latency",
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5]
)

health_check_latency_postgres = Histogram(
    "health_check_latency_postgres_seconds",
    "PostgreSQL health check latency",
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5]
)

# Маппинг сервисов к их гистограммам
_service_histograms = {
    "openai": health_check_latency_openai,
    "deepseek": health_check_latency_deepseek,
    "redis": health_check_latency_redis,
    "postgres": health_check_latency_postgres,
}


def _log_health_check(service: str, status: str, latency_ms: int = 0, reason: str | None = None) -> None:
    """Log health check result in structured JSON format to stdout."""
    log_entry = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "event": "health_check",
        "service": service,
        "status": status,
        "latency_ms": latency_ms,
    }
    if reason:
        log_entry["reason"] = reason
    
    print(json.dumps(log_entry), file=sys.stdout, flush=True)
    logger.info(f"Health check: {service} = {status}" + (f" ({reason})" if reason else ""))
    
    # Update Prometheus metrics
    latency_seconds = latency_ms / 1000.0
    
    # Общий счётчик и гистограмма
    health_check_total.labels(service=service, status=status).inc()
    health_check_duration_seconds.labels(service=service).observe(latency_seconds)
    
    # Специфичная гистограмма для сервиса
    if service in _service_histograms:
        _service_histograms[service].observe(latency_seconds)


async def check_openai(timeout: float = 5.0) -> dict:
    """Ping OpenAI API."""
    start = time.time()
    settings = get_settings()
    
    if not settings.openai_api_key:
        result = {"status": "down", "reason": "API key not configured"}
        _log_health_check("openai", "down", 0, "API key not configured")
        return result
    
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            )
            latency_ms = int((time.time() - start) * 1000)
            
            if resp.status_code == 200:
                _log_health_check("openai", "ok", latency_ms)
                return {"status": "ok", "latency_ms": latency_ms}
            else:
                reason = f"HTTP {resp.status_code}"
                _log_health_check("openai", "down", latency_ms, reason)
                return {"status": "down", "reason": reason}
    except asyncio.TimeoutError:
        latency_ms = int((time.time() - start) * 1000)
        _log_health_check("openai", "down", latency_ms, "timeout")
        return {"status": "down", "reason": "timeout"}
    except Exception as e:
        latency_ms = int((time.time() - start) * 1000)
        reason = str(e)
        _log_health_check("openai", "down", latency_ms, reason)
        return {"status": "down", "reason": reason}


async def check_deepseek(timeout: float = 5.0) -> dict:
    """Ping DeepSeek API."""
    start = time.time()
    settings = get_settings()
    
    if not settings.deepseek_api_key:
        result = {"status": "down", "reason": "API key not configured"}
        _log_health_check("deepseek", "down", 0, "API key not configured")
        return result
    
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(
                "https://api.deepseek.com/v1/models",
                headers={"Authorization": f"Bearer {settings.deepseek_api_key}"},
            )
            latency_ms = int((time.time() - start) * 1000)
            
            if resp.status_code == 200:
                _log_health_check("deepseek", "ok", latency_ms)
                return {"status": "ok", "latency_ms": latency_ms}
            else:
                reason = f"HTTP {resp.status_code}"
                _log_health_check("deepseek", "down", latency_ms, reason)
                return {"status": "down", "reason": reason}
    except asyncio.TimeoutError:
        latency_ms = int((time.time() - start) * 1000)
        _log_health_check("deepseek", "down", latency_ms, "timeout")
        return {"status": "down", "reason": "timeout"}
    except Exception as e:
        latency_ms = int((time.time() - start) * 1000)
        reason = str(e)
        _log_health_check("deepseek", "down", latency_ms, reason)
        return {"status": "down", "reason": reason}


async def check_redis(timeout: float = 3.0) -> dict:
    """Ping Redis."""
    start = time.time()
    
    try:
        import redis
        import os
        url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        client = redis.from_url(url, socket_connect_timeout=timeout)
        client.ping()
        latency_ms = int((time.time() - start) * 1000)
        _log_health_check("redis", "ok", latency_ms)
        return {"status": "ok", "latency_ms": latency_ms}
    except asyncio.TimeoutError:
        latency_ms = int((time.time() - start) * 1000)
        _log_health_check("redis", "down", latency_ms, "timeout")
        return {"status": "down", "reason": "timeout"}
    except Exception as e:
        latency_ms = int((time.time() - start) * 1000)
        reason = str(e)
        _log_health_check("redis", "down", latency_ms, reason)
        return {"status": "down", "reason": reason}


async def check_postgres(timeout: float = 3.0) -> dict:
    """Ping PostgreSQL."""
    start = time.time()
    
    try:
        # Run in executor to avoid blocking event loop
        def _ping():
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        
        await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(None, _ping),
            timeout=timeout
        )
        latency_ms = int((time.time() - start) * 1000)
        _log_health_check("postgres", "ok", latency_ms)
        return {"status": "ok", "latency_ms": latency_ms}
    except asyncio.TimeoutError:
        latency_ms = int((time.time() - start) * 1000)
        _log_health_check("postgres", "down", latency_ms, "timeout")
        return {"status": "down", "reason": "timeout"}
    except Exception as e:
        latency_ms = int((time.time() - start) * 1000)
        reason = str(e)
        _log_health_check("postgres", "down", latency_ms, reason)
        return {"status": "down", "reason": reason}


async def check_all_services() -> dict:
    """Check all services and return overall health status."""
    start = time.time()
    
    # Run all checks in parallel
    results = await asyncio.gather(
        check_openai(),
        check_deepseek(),
        check_redis(),
        check_postgres(),
        return_exceptions=True
    )
    
    openai_health, deepseek_health, redis_health, postgres_health = results
    
    services = {
        "openai": openai_health if isinstance(openai_health, dict) else {"status": "down", "reason": str(openai_health)},
        "deepseek": deepseek_health if isinstance(deepseek_health, dict) else {"status": "down", "reason": str(deepseek_health)},
        "redis": redis_health if isinstance(redis_health, dict) else {"status": "down", "reason": str(redis_health)},
        "postgres": postgres_health if isinstance(postgres_health, dict) else {"status": "down", "reason": str(postgres_health)},
    }
    
    # Determine overall status
    statuses = [s["status"] for s in services.values()]
    
    if all(s == "ok" for s in statuses):
        overall = "ok"
    elif services["postgres"]["status"] == "down":
        # Critical: DB down = app down
        overall = "down"
    elif services["openai"]["status"] == "down" and services["deepseek"]["status"] == "down":
        # Critical: all AI engines down
        overall = "down"
    else:
        # Some services degraded but app still usable
        overall = "degraded"
    
    total_latency_ms = int((time.time() - start) * 1000)
    
    # Log overall health check result
    log_entry = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "event": "health_check_summary",
        "status": overall,
        "total_latency_ms": total_latency_ms,
        "services_ok": sum(1 for s in statuses if s == "ok"),
        "services_down": sum(1 for s in statuses if s == "down"),
    }
    print(json.dumps(log_entry), file=sys.stdout, flush=True)
    logger.info(f"Health check summary: {overall} ({total_latency_ms}ms)")
    
    return {
        "status": overall,
        "services": services,
        "total_latency_ms": total_latency_ms,
    }
