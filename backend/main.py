"""Aristea Timeline — FastAPI application.

Endpoints:
  POST /api/v1/chart/calculate                  — compute natal chart
  GET  /api/v1/chart/{id}                       — retrieve saved chart
  GET  /api/v1/chart/{id}/interpret              — stream AI interpretation (SSE)
  GET  /api/v1/chart/{id}/transits               — calculate transits for period
  GET  /api/v1/chart/{id}/transits/interpret      — stream transit period interpretation (SSE)
  POST /api/v1/chart/{id}/transits/event/interpret — interpret single transit event (SSE)
  GET  /health                                   — app health
  GET  /health/db                                — database health
  GET  /health/ai                                — AI providers health
"""

from __future__ import annotations

from dotenv import load_dotenv
load_dotenv()  # загружает .env до всех os.getenv()

import asyncio
import json
import logging
import os
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from backend.time_utils import utcnow

from fastapi import APIRouter, FastAPI, Depends, HTTPException, Request
from pydantic import BaseModel
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler as _default_validation_handler
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse, Response
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy.orm import Session
from sqlalchemy import text

from backend.async_utils import replay_as_stream
from backend.config import get_settings
from backend.limiter import limiter
from backend.database import get_db, engine, Base
from backend.schemas import (
    BirthDataInput,
    NatalChartResponse,
    PlanetPosition,
    HouseData,
    AspectData,
    PointData,
    HealthResponse,
    ErrorResponse,
    TransitRequest,
    TransitEvent as TransitEventSchema,
    TransitResponse,
)
from backend.models import NatalChart
from backend.time_utils import local_today, user_tz
from backend.chart_points import UNKNOWN_TIME_HIDDEN, planets as natal_planets
from backend.ephemeris.calculator import calculate_full_chart
from backend.ephemeris.geo import (
    geocode_place,
    resolve_utc_datetime,
    applied_utc_offset_minutes,
    validate_coordinates,
    GeocodingError,
    AmbiguousTimeError,
)
from backend.cache import interpretation_cache, transit_cache, make_profile_hash
from backend.calendar.lunar_engine import get_monthly_calendar
from backend.auth.router import router as auth_router
from backend.flags import router as flags_router
from backend.profile.router import router as profile_router
from backend.profile.settings_router import router as settings_router
from backend.profile.email_unsubscribe import router as email_unsubscribe_router
from backend.onboarding_router import router as onboarding_router
from backend.push.router import router as push_router
from backend.push.cron import router as push_cron_router
from backend.share_router import router as share_router
from backend.advanced_charts_router import router as advanced_charts_router
from backend.payments.payments_router import router as payments_router
from backend.payments.yookassa_router import router as yookassa_router
from backend.crm.router import router as crm_router
from backend.crm.author_router import router as author_router
from backend.crm.portal_router import router as portal_router
from backend.crm.dashboard_router import router as crm_dashboard_router
from backend.crm.note_templates_router import router as note_templates_router
from backend.interpretation.rag_router import router as rag_router
from backend.admin.admin_router import router as admin_manage_router
from backend.admin.promo_router import router as promo_router
from backend.admin.stats_router import router as admin_stats_router
from backend.feedback.router import router as feedback_router
from backend.pilot.router import router as pilot_router
from backend.pilot.cron import router as pilot_cron_router
from backend.beat_watchdog import router as beat_watchdog_router
from backend.partners.router import router as partners_router, admin_router as partners_admin_router
from backend.exit_survey.router import router as exit_survey_router
from backend.crm.access_router import router as crm_access_router
from backend.calendar.export_router import router as calendar_export_router
from backend.metrics import log_event, maybe_mark_second_visit, EventName
from backend.auth.jwt import decode_token
from backend.database import SessionLocal
from backend.auth.dependencies import get_current_user_optional, get_current_user
from backend.auth.rate_limits import (
    tier_limiter, get_tier_limits, CHART_CREATION_ABUSE_LIMIT, check_chart_rate_limit,
    transits_date_window, planner_offset_window, guest_key, guest_limit,
)
from sqlalchemy import func as sa_func
from backend.models import User

logging.basicConfig(level=logging.INFO)  # без этого logger.info(...) нигде в бэкенде не долетал до stdout — только WARNING+
logger = logging.getLogger("astro")
settings = get_settings()

# ── Rate limiter ──
# Общий инстанс из backend.limiter: раньше здесь создавался второй Limiter, и
# счётчики main.py жили отдельно от счётчиков auth/admin-роутеров.
# Отключается в тестах через limiter.enabled = False в conftest.py


# ── Внутренний планировщик (замена Railway [cron.*]) ──
# Railway-кроны запускаются в отдельном одноразовом контейнере, где выполняется
# только command, а не startCommand — localhost:$PORT там ничего не слушает,
# и curl из railway.toml никогда не достукивался. Планируем тик внутри процесса.
_scheduler_task: asyncio.Task | None = None


async def _scheduler_loop():
    """In-process планировщик — только push-тик (каждые 15 минут).

    Еженедельный дайджест сюда раньше был продублирован (см. git-историю):
    эта функция слала его по понедельникам в 06:00 UTC, а Celery Beat
    (backend/celery_app.py, задача tasks.send_weekly_digest_task) — каждый
    день в 06:05 UTC, сама фильтруя по User.digest_day_of_week. У версии
    из этого файла было два независимых дефекта: она проверяла только
    `weekday() == 0`, то есть пользователи с дайджестом не по понедельникам
    не получали его вообще, а для пользователей С понедельником запуск обеих
    версий разом (после того как Beat наконец подняли) отправлял письмо
    дважды. Beat — единственный корректный и полный источник: он не привязан
    к тому же процессу, что держит HTTP-сервер, и переживает его рестарт.
    """
    from backend.push.cron import run_push_tick

    await asyncio.sleep(60)  # дать приложению подняться
    logger.info("Push scheduler started, interval 15m")

    while True:
        db = SessionLocal()
        try:
            result = await run_push_tick(db)
            logger.info("Push tick: users=%s delivered=%s", result.get("users"), result.get("delivered"))
        except Exception:
            logger.exception("Push tick failed")
        finally:
            db.close()

        await asyncio.sleep(15 * 60)


# ── Lifespan ──
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Схему на проде создаёт только `alembic upgrade head` (вызывается в
    # 05-update.sh). create_all строит таблицы напрямую из текущих ORM-моделей в
    # обход миграций: alembic_version остаётся пустой, и история миграций
    # расходится со схемой — см. предупреждение в deploy/opt-astro/README.md.
    if settings.testing or settings.debug:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables ensured (DEBUG/TESTING).")

    global _scheduler_task
    if os.getenv("SERVICE_ROLE") == "bot" or os.getenv("PUSH_SCHEDULER") == "off":
        logger.info("Push scheduler disabled (SERVICE_ROLE=bot or PUSH_SCHEDULER=off)")
    else:
        _scheduler_task = asyncio.create_task(_scheduler_loop())

    yield
    # Shutdown
    if _scheduler_task:
        _scheduler_task.cancel()
        try:
            await _scheduler_task
        except asyncio.CancelledError:
            pass
    logger.info("Shutting down.")


# ── App ──
app = FastAPI(
    title="Aristea Timeline API",
    version="0.1.0",
    description="Natal chart calculation, transits, AI interpretations",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Глобальный потолок на все маршруты. Без этого middleware default_limits в
# Limiter не действуют, и лимит есть только там, где явно висит декоратор.
# /health и /metrics освобождены ниже через @limiter.exempt: healthcheck Docker,
# Uptime Kuma и Prometheus опрашивают их постоянно и не должны упираться в лимит.
if settings.rate_limit_default and not settings.testing:
    from slowapi.middleware import SlowAPIMiddleware

    app.add_middleware(SlowAPIMiddleware)

# ── 422 логирование ──
# Ответ клиенту не меняется (делегируем в дефолтный обработчик FastAPI) —
# это только чтобы в логах было видно, какое поле и почему не прошло, вместо
# голого "422 Unprocessable Entity" без единой зацепки.
_SENSITIVE_BODY_KEYS = ("password", "token", "secret", "key", "authorization")


def _sanitize_body_for_log(value):
    if isinstance(value, dict):
        return {
            k: ("***" if any(s in k.lower() for s in _SENSITIVE_BODY_KEYS) else _sanitize_body_for_log(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_sanitize_body_for_log(v) for v in value]
    return value


@app.exception_handler(RequestValidationError)
async def _log_validation_errors(request: Request, exc: RequestValidationError):
    body = exc.body
    if isinstance(body, (bytes, bytearray)):
        try:
            body = json.loads(body)
        except Exception:
            body = "<unparseable body>"
    logger.warning(
        "422 validation error: %s %s errors=%s body=%s",
        request.method,
        request.url.path,
        exc.errors(),
        _sanitize_body_for_log(body),
    )
    return await _default_validation_handler(request, exc)


# ── Sentry ── (backend/sentry_setup.py; без SENTRY_DSN — ничего)
from backend.sentry_setup import init_sentry
init_sentry(settings.sentry_dsn, "api")

# ── TierMiddleware — пишет user_tier в request.state до декораторов лимитера ──
@app.middleware("http")
async def tier_middleware(request: Request, call_next):
    user_tier = "free"
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1]
        try:
            token_data = decode_token(token)
            user_tier = token_data.tier or "free"
        except Exception:
            user_tier = "free"
    request.state.user_tier = user_tier
    return await call_next(request)

# ── Проверка секрета подписи ──
# Дефолтный или короткий jwt_secret означает, что токены может выпустить кто
# угодно. В проде это должно валить старт, а не тихо работать.
_INSECURE_JWT_SECRETS = {"CHANGE-ME-IN-PRODUCTION", "", "secret", "changeme"}
MIN_JWT_SECRET_LENGTH = 32

if not (settings.debug or settings.testing):
    if settings.jwt_secret in _INSECURE_JWT_SECRETS:
        raise RuntimeError(
            "JWT_SECRET не задан или равен значению-заглушке. "
            "Сгенерируйте секрет: python -c \"import secrets; print(secrets.token_urlsafe(48))\""  # вы-разрешено: владельцу при запуске
        )
    if len(settings.jwt_secret) < MIN_JWT_SECRET_LENGTH:
        raise RuntimeError(
            f"JWT_SECRET короче {MIN_JWT_SECRET_LENGTH} символов "
            f"({len(settings.jwt_secret)}) — подберётся перебором."
        )

    # ── Служебные эндпоинты ──
    # Без секрета require_internal_secret отдаёт 503, то есть выдача pilot-токенов
    # и массовые рассылки просто перестанут работать. Падать на старте честнее,
    # чем обнаружить это по молчащему крону.
    if not os.getenv("INTERNAL_SECRET"):
        raise RuntimeError(
            "INTERNAL_SECRET не задан — служебные эндпоинты /api/v1/internal/* "
            "не смогут работать. Сгенерируйте: "
            "python -c \"import secrets; print(secrets.token_urlsafe(32))\""  # вы-разрешено: владельцу при запуске
        )

    # ── Платежи (ЮKassa) ──
    # Тот же набор проверок продублирован в deploy/opt-astro/05-update.sh.
    # Дубль не лишний: проверка только в приложении означает, что о проблеме
    # узнаёшь на середине деплоя, когда старый контейнер уже погашен, — так
    # прод падал дважды (см. CLAUDE.md, раздел «Деплой»).
    #
    # 23.08.2026: переменные стали ОБЯЗАТЕЛЬНЫМИ. Раньше пустая пара считалась
    # нормой — платежи просто не активны, checkout отвечал 503. Это было удобно
    # до запуска, но магазин зарегистрирован и оплата объявлена пользователям:
    # теперь пустой .env означает, что кнопка «оплатить» молча не работает, а
    # узнать об этом можно только от пользователя. Отказ на старте — громкий и
    # немедленный, деплой при этом откатится на предыдущий образ сам.
    if not settings.yookassa_shop_id or not settings.yookassa_secret_key:
        raise RuntimeError(
            "YOOKASSA_SHOP_ID и YOOKASSA_SECRET_KEY обязательны в боевом окружении: "
            "без них /payments/checkout отвечает 503, то есть оплата не работает, "
            "хотя объявлена пользователям. Задайте обе переменные в /opt/astro/.env "
            "(магазин 1442186). Для локальной разработки без платежей используйте "
            "DEBUG=true или TESTING=true."  # вы-разрешено: владельцу при запуске
        )
    # Проверка ниже после введения обязательности недостижима в проде (пустая
    # половина уже упала выше) и оставлена намеренно: она страхует на случай,
    # если обязательность когда-нибудь снова смягчат, и сохраняет отдельную
    # внятную формулировку про половинчатую конфигурацию. Не удалять как
    # «мёртвый код».
    if bool(settings.yookassa_shop_id) != bool(settings.yookassa_secret_key):
        raise RuntimeError(
            "ЮKassa настроена наполовину: задана только одна из YOOKASSA_SHOP_ID / "
            "YOOKASSA_SECRET_KEY. Задайте обе или ни одной — половина конфигурации "
            "означает checkout, который создаёт платежи, но не может проверить вебхук "
            "(или наоборот)."  # вы-разрешено: владельцу при запуске
        )
    if settings.yookassa_secret_key.startswith("test_"):
        raise RuntimeError(
            "YOOKASSA_SECRET_KEY — тестовый ключ (test_...) в боевом окружении. "
            "В тестовом режиме ЮKassa «оплата» проходит без реальных денег, то есть "
            "подписки выдавались бы бесплатно. Подставьте боевой ключ магазина."  # вы-разрешено: владельцу при запуске
        )

# ── Доверенные прокси ──
# Без этого request.client.host остаётся адресом прокси. Список строгий:
# "*" здесь означал бы, что любой клиент подделает свой IP заголовком.
if settings.trusted_proxy_ips:
    from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

    app.add_middleware(
        ProxyHeadersMiddleware,
        trusted_hosts=[h.strip() for h in settings.trusted_proxy_ips.split(",") if h.strip()],
    )
else:
    logger.warning(
        "TRUSTED_PROXY_IPS не задан — X-Forwarded-For игнорируется, "
        "лимиты считаются по адресу прокси."
    )

# ── CORS ──
# Списки явные, а не ["*"]: с allow_credentials=True браузер и так отвергает
# "*", а Starlette в ответ на preflight отражает запрошенные значения —
# фактически разрешая любой метод и заголовок.
CORS_ALLOW_METHODS = ["GET", "POST", "PATCH", "DELETE", "OPTIONS"]
# X-Client-Platform: им мобильный клиент (Capacitor) просит отдать refresh-токен
# в теле ответа вместо HttpOnly-куки — webview ходит с origin https://localhost,
# и SameSite=Strict куку туда не отдаёт. Подробности — backend/auth/router.py.
CORS_ALLOW_HEADERS = ["Authorization", "Content-Type", "X-Chart-Token", "X-Client-Platform"]

# Сочетание allow_credentials=True с "*" в origins недопустимо: браузер
# отбросит такой ответ, а на сервере это тихая ошибка конфигурации.
if "*" in settings.cors_origins_list:
    message = (
        "ALLOWED_ORIGINS содержит '*' вместе с allow_credentials=True — "
        "укажите конкретные origins."  # вы-разрешено: владельцу при запуске
    )
    if settings.debug or settings.testing:
        logger.error(message)
    else:
        raise RuntimeError(message)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=CORS_ALLOW_METHODS,
    allow_headers=CORS_ALLOW_HEADERS,
)

# ── Host header ──
# Наверх Nginx передаёт Host как есть (proxy_set_header Host $host), поэтому
# подделанный Host долетает до приложения и попадает в ссылки писем и в кэш.
# По умолчанию ALLOWED_HOSTS пуст → ["*"], поведение прежнее.
if settings.allowed_hosts_list != ["*"]:
    from starlette.middleware.trustedhost import TrustedHostMiddleware

    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts_list)

# ── Routers ──
app.include_router(auth_router)
app.include_router(flags_router)
app.include_router(profile_router)
app.include_router(settings_router)
app.include_router(email_unsubscribe_router)
app.include_router(onboarding_router)
app.include_router(push_router)
app.include_router(push_cron_router)
app.include_router(share_router)
app.include_router(advanced_charts_router)
app.include_router(payments_router)
app.include_router(yookassa_router)
app.include_router(crm_router)
app.include_router(author_router)
app.include_router(portal_router)
app.include_router(crm_dashboard_router)
app.include_router(note_templates_router)
app.include_router(rag_router)
app.include_router(promo_router)
app.include_router(admin_stats_router)
app.include_router(admin_manage_router)
app.include_router(feedback_router)
app.include_router(pilot_router)
app.include_router(pilot_cron_router)
app.include_router(beat_watchdog_router)
app.include_router(partners_router)
app.include_router(partners_admin_router)
app.include_router(exit_survey_router)
app.include_router(crm_access_router)
app.include_router(calendar_export_router)
# Лента событий: транзиты + планер + лунный календарь одним ответом.
# Импорт здесь, а не в шапке файла: feed/router.py при загрузке карты
# отложенно импортирует backend.main, и импорт наверху замкнул бы цикл.
from backend.feed.router import router as feed_router  # noqa: E402
app.include_router(feed_router)

# Прогнозы для приложения: на сегодня и на новолуние/полнолуние.
from backend.forecast.router import router as forecast_router  # noqa: E402
app.include_router(forecast_router)

# PDF-отчёты в фоне (backend/pdf_reports). Старый POST /chart/{id}/pdf ниже
# остаётся для старых APK.
from backend.pdf_reports.router import router as pdf_reports_router  # noqa: E402
app.include_router(pdf_reports_router)

# Первая неделя по сценарию (флаг first_week, backend/first_week.py).
from backend.first_week_router import router as first_week_router  # noqa: E402
app.include_router(first_week_router)

# «Неделя вперёд» (флаг week_ahead, backend/week_ahead.py).
from backend.week_ahead_router import router as week_ahead_router  # noqa: E402
app.include_router(week_ahead_router)

# Карточка дня для сторис (флаг story_card, backend/story_card.py).
from backend.story_card_router import router as story_card_router  # noqa: E402
app.include_router(story_card_router)

# Виджет «День» на главный экран Android (флаг widget, backend/widget.py).
from backend.widget_router import router as widget_router  # noqa: E402
app.include_router(widget_router)


# ═══════════════════════════════════════════════════════════
# PROMETHEUS METRICS
# ═══════════════════════════════════════════════════════════

@app.get("/metrics", tags=["monitoring"], summary="Prometheus metrics endpoint")
@limiter.exempt
def metrics():
    """Expose Prometheus metrics."""
    from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


# ═══════════════════════════════════════════════════════════
# HEALTH ENDPOINTS
# ═══════════════════════════════════════════════════════════


@app.get("/health", response_model=HealthResponse, tags=["health"])
@limiter.exempt
async def health():
    return HealthResponse(status="ok", version="0.1.0", database="not_checked")


@app.get("/health/db", response_model=HealthResponse, tags=["health"])
@limiter.exempt
def health_db(db: Session = Depends(get_db)):
    # Текст исключения наружу не отдаём: ошибки SQLAlchemy/psycopg2 содержат хост,
    # порт, имя БД и пользователя, а /health проксируется в интернет. Подробности —
    # в лог.
    try:
        db.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception:
        logger.exception("health/db check failed")
        db_status = "error"
    return HealthResponse(status="ok", version="0.1.0", database=db_status)


# ── Debug-роуты ──
# Регистрируются только при DEBUG/TESTING: в проде их не должно быть ни в
# приложении, ни в /openapi.json. Подключение — в конце модуля, после того
# как все debug-эндпоинты объявлены.
debug_router = APIRouter(tags=["debug"])
DEBUG_ROUTES_ENABLED = settings.debug or settings.testing


# ═══════════════════════════════════════════════════════════
# CHART ACCESS
# ═══════════════════════════════════════════════════════════

def new_anon_chart_credentials() -> tuple[str, datetime]:
    """Токен доступа и срок жизни для новой анонимной карты."""
    return (
        secrets.token_urlsafe(32),
        utcnow() + timedelta(days=settings.anon_chart_ttl_days),
    )


def resolve_chart_access(
    chart_id: str,
    user: User | None,
    token: str | None,
    db: Session,
) -> NatalChart:
    """Вернуть карту, если запрашивающий имеет на неё право, иначе 404.

    Правила:
      - карта с user_id — только владельцу;
      - анонимная карта — по совпадающему непросроченному access_token.

    Везде 404, а не 403: ответ не должен раскрывать существование чужой карты.
    """
    chart = db.query(NatalChart).filter(NatalChart.id == chart_id).first()
    if chart is None:
        raise HTTPException(status_code=404, detail=f"Chart not found: {chart_id}")

    if chart.user_id is not None:
        if user is not None and chart.user_id == user.id:
            return chart
        raise HTTPException(status_code=404, detail=f"Chart not found: {chart_id}")

    # Анонимная карта: сверяем capability-токен в постоянное время.
    if (
        token
        and chart.access_token
        and secrets.compare_digest(token, chart.access_token)
        and not (chart.expires_at and chart.expires_at < utcnow())
    ):
        return chart

    raise HTTPException(status_code=404, detail=f"Chart not found: {chart_id}")


def _ensure_chart_slot(user: User, db: Session) -> None:
    """403, если все слоты карт тарифа заняты (profiles_limit). Общая для
    построения карты и привязки анонимной (claim_chart): привязка тоже
    занимает слот, и без проверки через гостевой режим обходился бы лимит."""
    tier = user.tier or "free"
    profiles_limit = get_tier_limits(tier).get("profiles_limit")
    if profiles_limit is None:
        return
    total_charts = (
        db.query(sa_func.count(NatalChart.id))
        .filter(NatalChart.user_id == user.id)
        .scalar() or 0
    )
    if total_charts >= profiles_limit:
        from backend.email_service import TIER_NAMES
        raise HTTPException(
            status_code=403,
            detail=(
                f"Достигнут лимит сохранённых карт ({profiles_limit}) для тарифа "
                f"{TIER_NAMES.get(tier, tier.capitalize())}. Удали ненужную карту, чтобы "
                f"освободить место, или перейди на старший тариф."
            ),
        )


def chart_token(request: Request) -> str | None:
    """Capability-токен анонимной карты из заголовка X-Chart-Token."""
    return request.headers.get("X-Chart-Token")


# ═══════════════════════════════════════════════════════════
# CHART ENDPOINTS
# ═══════════════════════════════════════════════════════════

@app.post(
    "/api/v1/chart/calculate",
    response_model=NatalChartResponse,
    responses={422: {"model": ErrorResponse}, 400: {"model": ErrorResponse}},
    tags=["chart"],
    summary="Calculate natal chart",
)
@limiter.limit(settings.rate_limit_anon)
# Гостю — не больше 20 анонимных карт в сутки с одного IP (rate_limits.guest_key).
# ⚠️ Лимит общий с веб-лендингом (он тоже строит анонимные карты), а за одним
# IP мобильного оператора (CGNAT) сидят многие — поэтому не меньше 20.
@limiter.limit(guest_limit("20/day"), key_func=guest_key)
async def calculate_chart(
    request: Request,
    data: BirthDataInput,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    """Calculate a natal chart from birth data.

    Accepts date, optional time, and place of birth.
    Returns full chart with planets, houses, aspects, ASC, MC.
    """
    return await _build_chart(request, data, db, user)


# Демо-карта веб-лендинга («Показать пример»). Данные — серверные: клиент
# шлёт только сам факт демо (решение владельца 27.09.2026). Согласие на
# обработку здесь не нужно — данных человека в запросе нет. Флага «пропусти
# проверку согласия» у calculate нет намеренно: им обходилась бы проверка.
DEMO_BIRTH = BirthDataInput(
    name="Александр", birth_date=datetime(1996, 5, 28).date(), birth_time="11:50",
    birth_place="Москва, Россия", house_system="placidus",
)


@app.post("/api/v1/chart/demo", response_model=NatalChartResponse, tags=["chart"],
          summary="Демо-карта по серверным данным")
@limiter.limit(settings.rate_limit_anon)
@limiter.limit(guest_limit("20/day"), key_func=guest_key)
async def demo_chart(request: Request, db: Session = Depends(get_db)):
    """Всегда анонимная — и у вошедшего: чужая демонстрационная карта не
    должна занимать слот его тарифа."""
    return await _build_chart(request, DEMO_BIRTH, db, None, demo=True)


async def _build_chart(request: Request, data: BirthDataInput, db: Session,
                       user: User | None, *, demo: bool = False):
    # Без входа дата, время и место рождения обрабатываются до флажка на
    # регистрации — нужна галочка согласия (решение владельца 27.09.2026).
    # Включено после выката галочки в обеих формах (приложение, веб-лендинг).
    # Демо не проверяется: данных человека в нём нет (DEMO_BIRTH), и признак
    # демо клиент не присылает — это отдельная ручка, обойти ею нечего.
    if user is None and not demo and not data.consent:
        raise HTTPException(
            status_code=422,
            detail="Отметь согласие на обработку даты, времени и места рождения.",
        )
    await check_chart_rate_limit(user, request)

    warnings: list[str] = []

    # 1. Geocode the birth place
    try:
        geo = await geocode_place(data.birth_place)
    except GeocodingError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 2. Validate coordinates
    try:
        coord_warnings = validate_coordinates(geo.latitude, geo.longitude)
        warnings.extend(coord_warnings)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 3. Resolve UTC datetime (handles DST edge-cases)
    try:
        utc_dt, time_unknown, tz_warnings = resolve_utc_datetime(
            birth_date=str(data.birth_date),
            birth_time=data.birth_time,
            timezone=geo.timezone,
            utc_offset_minutes=data.utc_offset_minutes,
        )
        warnings.extend(tz_warnings)
    except AmbiguousTimeError as e:
        raise _ambiguous_time_http(e)

    # 4. Calculate chart
    try:
        # Swiss Ephemeris — синхронный, блокирует единственный event loop
        # процесса (см. CLAUDE.md). asyncio.to_thread — не напрямую.
        (chart_data, aspects) = await asyncio.to_thread(
            calculate_full_chart,
            utc_dt=utc_dt,
            latitude=geo.latitude,
            longitude=geo.longitude,
            house_system=data.house_system,
            time_unknown=time_unknown,
        )
        warnings.extend(chart_data.warnings)
    except Exception as e:
        logger.exception("Chart calculation failed")
        raise HTTPException(status_code=500, detail=f"Calculation error: {e}")

    # 5. Build response objects
    planets_resp = [
        PlanetPosition(
            name=p.name,
            longitude=p.longitude,
            sign=p.sign,
            degree_in_sign=p.degree_in_sign,
            house=p.house if not time_unknown else None,
            retrograde=p.retrograde,
        )
        for p in chart_data.planets
    ]

    houses_resp = [
        HouseData(number=h.number, sign=h.sign, degree=h.degree)
        for h in chart_data.houses
    ]

    aspects_resp = [
        AspectData(
            planet1=a.planet1,
            planet2=a.planet2,
            aspect_type=a.aspect_type,
            angle=a.angle,
            orb=a.orb,
            applying=a.applying,
            importance=getattr(a, "importance", "low"),
        )
        for a in aspects
    ]

    asc_resp = PointData(
        sign=chart_data.ascendant.sign,
        degree=chart_data.ascendant.degree,
        longitude=chart_data.ascendant.longitude,
    ) if chart_data.ascendant else None

    mc_resp = PointData(
        sign=chart_data.midheaven.sign,
        degree=chart_data.midheaven.degree,
        longitude=chart_data.midheaven.longitude,
    ) if chart_data.midheaven else None

    # 6. Persist to database (only for authenticated users)
    chart_record = NatalChart(
        user_id=user.id if user else None,
        name=data.name,
        birth_date=str(data.birth_date),
        birth_time=data.birth_time,
        birth_place=geo.display_name,
        latitude=geo.latitude,
        longitude=geo.longitude,
        timezone=geo.timezone,
        utc_datetime=utc_dt,
        utc_offset_manual=data.utc_offset_minutes is not None,
        time_unknown=time_unknown,
        house_system=data.house_system,
        planets=[p.model_dump() for p in planets_resp],
        houses=[h.model_dump() for h in houses_resp],
        aspects=[a.model_dump() for a in aspects_resp],
        ascendant=asc_resp.model_dump() if asc_resp else None,
        midheaven=mc_resp.model_dump() if mc_resp else None,
    )

    if user:
        tier = user.tier or "free"
        limits = get_tier_limits(tier)
        daily_limit = limits.get("charts_per_day")

        now = utcnow()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        # Лимит карт на аккаунт (profiles_limit) — слотовая модель: сколько
        # карт одновременно может быть сохранено (семья, партнёр, дети —
        # см. /pricing), не месячная квота. Удаление карты освобождает слот.
        # Раньше число только отображалось в интерфейсе и нигде не
        # проверялось: на витрине «до N карт», а технически можно было
        # создать сколько угодно (19.08.2026, решение владельца — ввести
        # проверку без исключений для уже существующих данных, на проде
        # пользователей ещё нет). Проверяется ПЕРЕД защитой от ботов ниже —
        # это тот лимит, что реально описан на /pricing, и единственный,
        # где «удалите карту» — рабочий совет пользователю.
        _ensure_chart_slot(user, db)

        # Защита от ботов/скриптов — не тарифная фича, нигде не описана и не
        # обещана (20.08.2026, решение владельца). Одно число на все тарифы:
        # для free/lite/pro оно недостижимо (profiles_limit блокирует
        # намного раньше), реальный смысл имеет только для Orion, где слотов
        # без ограничения. Сообщение намеренно не упоминает ни «удали
        # карту» (это подсказка, как обойти защиту), ни «перейди на
        # тариф выше» (бессмысленно для Orion, который и так старший).
        charts_this_month = (
            db.query(sa_func.count(NatalChart.id))
            .filter(NatalChart.user_id == user.id, NatalChart.created_at >= month_start)
            .scalar() or 0
        )
        if charts_this_month >= CHART_CREATION_ABUSE_LIMIT:
            raise HTTPException(
                status_code=403,
                detail="Слишком много карт создано за последнее время. Попробуй чуть позже.",
            )

        if daily_limit is not None:
            day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            charts_today = (
                db.query(sa_func.count(NatalChart.id))
                .filter(NatalChart.user_id == user.id, NatalChart.created_at >= day_start)
                .scalar() or 0
            )
            if charts_today >= daily_limit:
                raise HTTPException(
                    status_code=403,
                    detail=f"Достигнут лимит карт для тарифа {tier}: {daily_limit} в день",
                )

        db.add(chart_record)
        db.commit()
        db.refresh(chart_record)
    else:
        # Anonymous — сохраняем с временным capability-токеном (7 дней),
        # чтобы у карты был реальный id и доступ к планеру/транзитам до
        # регистрации. При регистрации карта привязывается к пользователю.
        chart_record.access_token = secrets.token_urlsafe(32)
        chart_record.expires_at = utcnow() + timedelta(days=7)
        if data.consent:
            from backend.auth.consent import CURRENT_PRIVACY_VERSION
            chart_record.consent_given_at = utcnow()
            chart_record.consent_privacy_version = CURRENT_PRIVACY_VERSION
        db.add(chart_record)
        db.commit()
        db.refresh(chart_record)
    _queue_sky_warm(db, chart_record)

    # Welcome-письмо после первой карты. Письма day2/day7/day14 отсюда больше
    # не ставятся: их шлёт Beat от даты регистрации (backend/lifecycle_emails.py).
    if user:
        prev_charts = db.query(NatalChart).filter(
            NatalChart.user_id == user.id,
            NatalChart.id != chart_record.id,
        ).count()
        from backend.profile.email_unsubscribe import unsubscribe_url
        unsub_url = unsubscribe_url(user)
        if prev_charts == 0 and unsub_url:
            from backend.email_service import send_welcome_email
            try:
                await send_welcome_email(
                    to=user.email,
                    planets=[p.model_dump() for p in planets_resp],
                    unsubscribe_url=unsub_url,
                )
            except Exception as e:
                logger.warning("Welcome email failed: %s", e)

    return NatalChartResponse(
        id=chart_record.id,
        name=chart_record.name,
        birth_date=str(data.birth_date),
        birth_time=data.birth_time,
        birth_place=geo.display_name,
        latitude=geo.latitude,
        longitude=geo.longitude,
        timezone=geo.timezone,
        utc_offset_minutes=applied_utc_offset_minutes(str(data.birth_date), data.birth_time, utc_dt),
        utc_offset_source="manual" if data.utc_offset_minutes is not None else "place",
        time_unknown=time_unknown,
        house_system=data.house_system,
        planets=planets_resp,
        houses=houses_resp,
        aspects=aspects_resp,
        ascendant=asc_resp,
        midheaven=mc_resp,
        warnings=warnings,
        access_token=(chart_record.access_token if user is None else None),
    )


def _ambiguous_time_http(e: AmbiguousTimeError) -> HTTPException:
    """400 на время из часа перевода стрелок назад.

    `offsets` — парой к `options`: клиент отправляет выбранное смещение в
    `utc_offset_minutes`, и повторный запрос уже однозначен. `options`
    оставлены прежними строками ради уже установленных APK.
    """
    return HTTPException(
        status_code=400,
        detail={
            "message": str(e),
            "options": e.options,
            "offsets": e.offsets,
            "type": "ambiguous_time",
        },
    )


@app.post("/api/v1/chart/{chart_id}/claim", tags=["chart"], summary="Привязать анонимную карту к аккаунту")
async def claim_chart(
    chart_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Гость приложения построил карту до регистрации — после входа она
    переходит на аккаунт ТОЙ ЖЕ строкой (27.09.2026).

    ⚠️ Прежний `save-anonymous` (удалён 27.09.2026) пересчитывал карту заново и создавал вторую
    строку, а анонимная остаётся висеть до чистки — дубль в метриках и лишний
    пересчёт. Здесь меняется владелец, id карты прежний: лента, кэш прогноза и
    разбор на устройстве продолжают работать без перезапроса.

    Токен доступа и срок гасятся: после привязки карта — обычная карта
    аккаунта, и старый токен с устройства (или из утёкшего лога) её больше
    не открывает. Повторный вызов владельцем — 200 без изменений.
    """
    chart = db.query(NatalChart).filter(NatalChart.id == chart_id).first()
    if chart is not None and chart.user_id == user.id:
        return {"id": chart.id, "claimed": False}
    # Право — только по токену анонимной карты: чужая или просроченная — 404.
    chart = resolve_chart_access(chart_id, None, chart_token(request), db)
    _ensure_chart_slot(user, db)
    chart.user_id = user.id
    chart.access_token = None
    chart.expires_at = None
    if not user.primary_chart_id:
        user.primary_chart_id = chart.id
    db.commit()
    logger.info("Chart %s claimed by user %s", chart.id, user.id)
    # Приветственное письмо «первая карта» — как после построения, один раз
    # (журнал email_sent_log). Через Celery: send_once синхронный и сам
    # запускает event loop, из этого обработчика его звать нельзя.
    try:
        from backend.tasks import send_claim_welcome_task
        send_claim_welcome_task.delay(user.id, chart.id)
    except Exception as e:  # noqa: BLE001 — письмо не должно ронять привязку
        logger.warning("claim welcome not queued: %s", e)
    _queue_sky_warm(db, chart)
    return {"id": chart.id, "claimed": True}


def _queue_sky_warm(db: Session, chart) -> None:
    """Под флагом `sky_event` — прогреть чанки ядра в фоне (backend/sky.py,
    «Прогрев»): первый же прогноз или виджет не должен считать их в запросе."""
    try:
        from backend.day_event import SKY_FLAG
        from backend.flags import flag_on
        if flag_on(db, SKY_FLAG, chart.user_id):
            from backend.tasks import sky_warm
            sky_warm.delay(chart.id)
    except Exception as e:  # noqa: BLE001 — прогрев не должен ронять сохранение карты
        logger.warning("sky warm not queued: %s", e)


@app.get(
    "/api/v1/chart/{chart_id}",
    response_model=NatalChartResponse,
    responses={404: {"model": ErrorResponse}},
    tags=["chart"],
    summary="Get saved chart",
)
@limiter.limit(settings.rate_limit_anon)
async def get_chart(
    request: Request,
    chart_id: str,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    """Retrieve a previously calculated natal chart by ID."""
    chart = resolve_chart_access(chart_id, user, chart_token(request), db)

    planets = [PlanetPosition(**p) for p in chart.planets]
    houses = [HouseData(**h) for h in chart.houses]
    # Deduplicate aspects from DB (guards against legacy duplicates)
    seen_aspects: dict[tuple, AspectData] = {}
    for a in chart.aspects:
        asp = AspectData(**a)
        key = (frozenset([asp.planet1, asp.planet2]), asp.aspect_type)
        if key not in seen_aspects or asp.orb < seen_aspects[key].orb:
            seen_aspects[key] = asp
    aspects = list(seen_aspects.values())
    asc = PointData(**chart.ascendant) if chart.ascendant else None
    mc = PointData(**chart.midheaven) if chart.midheaven else None

    from backend.models import Interpretation
    has_interpretation = (
        db.query(Interpretation.id)
        .filter(Interpretation.chart_id == chart.id)
        .first()
    ) is not None

    return NatalChartResponse(
        id=chart.id,
        name=chart.name,
        has_interpretation=has_interpretation,
        free_interpretation_used=bool(
            getattr(chart, "free_interpretation_used", False)
        ),
        birth_date=chart.birth_date,
        birth_time=chart.birth_time,
        birth_place=chart.birth_place,
        latitude=chart.latitude,
        longitude=chart.longitude,
        timezone=chart.timezone,
        utc_offset_minutes=applied_utc_offset_minutes(
            chart.birth_date, chart.birth_time, chart.utc_datetime,
        ),
        utc_offset_source="manual" if getattr(chart, "utc_offset_manual", False) else "place",
        time_unknown=chart.time_unknown,
        house_system=chart.house_system,
        planets=planets,
        houses=houses,
        aspects=aspects,
        ascendant=asc,
        midheaven=mc,
    )


# ═══════════════════════════════════════════════════════════
# INTERPRETATION ENDPOINTS
# ═══════════════════════════════════════════════════════════


def _save_chart_interpretation(db, chart, profile: dict, chunks: list[str], interp_request) -> None:
    """Сохранить разбор карты после ПОЛНОСТЬЮ доставленного стрима.

    Зачем: до 30.08.2026 строку в Interpretation писали только PDF-пути
    (этот файл и tasks.py). SSE-путь не писал ничего, поэтому прочитанный на
    экране разбор нигде не оставался: закрыл вкладку — текст исчез, а право
    на него сгорело (chart.free_interpretation_used). Перечитать было нельзя
    ни на одном тарифе.

    Вызывать ТОЛЬКО из ветки, где стрим завершился штатно. Половина разбора в
    базе хуже его отсутствия: человек откроет обрубок, а право будет
    потрачено. Отдельной проверки «доставлено целиком» здесь нет и не нужно —
    её уже делает router.stream(): при finish_reason != "stop" он поднимает
    IncompleteInterpretation, управление уходит в except и сюда не приходит.
    Тот же приём, что у разбора транзитного события ниже в этом файле:
    накопленный collected сохраняется только после [DONE].

    Дубль не создаём: как и PDF-путь, при уже существующей строке просто
    ничего не делаем. Гонка двух вкладок теоретически даст две строки — обе
    читающие стороны берут последнюю по created_at, поведение то же, что уже
    было у PDF.

    Ошибку записи глушим: разбор пользователю уже доставлен, и падение после
    [DONE] испортило бы успешный ответ ради журнала.
    """
    from backend.models import Interpretation

    content = "".join(chunks).strip()
    if not content:
        return

    exists = (
        db.query(Interpretation.id)
        .filter(Interpretation.chart_id == chart.id)
        .first()
    )
    if exists:
        return

    try:
        from backend.cache import make_profile_hash
        db.add(Interpretation(
            chart_id=chart.id,
            profile_hash=make_profile_hash(profile),
            # Настоящий движок, а не заглушка: иначе учёт разъедется. Роутер
            # называет его в interp_request.engine_used — поле лежит на
            # объекте запроса, а не на роутере, потому что тот синглтон
            # (см. interpretation/base.py).
            engine=getattr(interp_request, "engine_used", None) or "unknown",
            content=content,
            sections=None,
            # Тариф разбора (067): PDF берёт разбор не короче тарифа человека.
            tier=interp_request.tier,
        ))
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Не удалось сохранить разбор карты %s", chart.id)


def _finish_event(reason):
    """Событие с причиной завершения — последнее перед [DONE].

    Заведено 09.09.2026. До него клиент мог узнать «текст полон» только по
    наличию самого маркера [DONE]: настоящий finish_reason провайдера наружу
    не выходил, и вывод «пришёл [DONE], значит stop» был рассуждением по
    коду, а не прочитанным фактом. Рассуждение верное, но оно ломается от
    любой будущей правки, которая начнёт отдавать [DONE] на новом пути, — и
    ломается молча.

    ⚠️ Пользователю это поле не показывать: оно про механику стрима, а не
    про разбор. Никакой текст из него не собирается.

    ⚠️ Поле НЕОБЯЗАТЕЛЬНОЕ, и старые клиенты обязаны его пережить. Они и
    переживают: в `_connectSSE` (`frontend/src/api/client.js`) событие без
    `type`, `text` и `error` не попадает ни в одну ветку разбора и молча
    отбрасывается; мобильный клиент ходит тем же транспортом. Поэтому
    событие ОТДЕЛЬНОЕ, а не поле внутри [DONE]: [DONE] сравнивается со
    строкой целиком, и любая добавка в него сломала бы обоих клиентов разом.
    """
    payload = json.dumps({"finish_reason": reason}, ensure_ascii=False)
    return "data: " + payload + '\n\n'


@app.get(
    "/api/v1/chart/{chart_id}/interpret",
    tags=["interpretation"],
    summary="Stream AI interpretation (SSE)",
)
@limiter.limit(settings.rate_limit_anon)
async def interpret_chart(
    request: Request,
    chart_id: str,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    """Stream an AI-generated interpretation of a natal chart via Server-Sent Events.

    The response is streamed token-by-token for a smooth UX.
    Fallback chain: GPT-4o → DeepSeek V3 → Template engine.
    """
    from backend.interpretation.base import InterpretationRequest
    from backend.interpretation.router import get_router, IncompleteInterpretation

    # Проверка лимита переехала ПОСЛЕ resolve_chart_access: с 048 бесплатный
    # разбор Free считается по карте, а не по аккаунту, и карту сначала надо
    # получить. Следствие: Free с исчерпанным правом, спросивший чужую или
    # несуществующую карту, получает 404 вместо прежнего 403. Не утечка —
    # resolve_chart_access отвечает 404 одинаково на «нет карты» и «нет доступа».
    chart = resolve_chart_access(chart_id, user, chart_token(request), db)

    # Отказ по лимиту уезжает ПЕРВЫМ СОБЫТИЕМ В ПОТОКЕ, а не HTTP-статусом.
    # EventSource не даёт JS доступа ни к коду ответа, ни к телу: браузер
    # сообщает только «ошибка». Прежний 403 до открытия StreamingResponse
    # означал, что текст «Вы использовали бесплатную интерпретацию…» до
    # пользователя не доезжал вовсе — после трёх реконнектов он видел
    # «Соединение прервалось». Клиент (_connectSSE в api/client.js) на событие
    # с полем error закрывает соединение сам, поэтому реконнектов теперь нет:
    # ответ 200, обрыва транспорта не происходит.
    #
    # Аноним — исключение, ему по-прежнему настоящий 403: для SSE этот статус
    # работает ещё и как отказ по аутентификации (ходят по одноразовому
    # тикету), и на нём держится одноразовость тикета (test_sse_tickets.py).
    # Готовый разбор этой карты отдаём БЕЗ проверки лимита: за него уже
    # заплачено (или потрачено бесплатное право), и повторное чтение своего
    # текста ничего не стоит — генерации не будет. Лимит остаётся ровно там,
    # где тратятся деньги: перед созданием НОВОГО разбора.
    #
    # До 30.08.2026 гейт стоял раньше всего, поэтому человек с исчерпанным
    # правом не получал даже собственный, уже оплаченный текст.
    #
    # Аноним намеренно исключён: ему по-прежнему настоящий 403 (см. ниже),
    # на этом статусе держится одноразовость SSE-тикета
    # (test_sse_tickets.py). Короткое замыкание для него сломало бы контракт.
    saved_interpretation = None
    if user is not None:
        from backend.models import Interpretation
        saved_interpretation = (
            db.query(Interpretation)
            .filter(Interpretation.chart_id == chart_id)
            .order_by(Interpretation.created_at.desc())
            .first()
        )

    limit_error: str | None = None
    if saved_interpretation is None:
        try:
            tier_limiter.check_interpretation_limit(user, db, chart=chart)
        except HTTPException as exc:
            if user is None or not isinstance(exc.detail, str):
                raise
            limit_error = exc.detail

    # Build natal profile from stored data
    profile = {
        "planets": chart.planets,
        "houses": chart.houses,
        "aspects": chart.aspects,
        "ascendant": chart.ascendant,
        "midheaven": chart.midheaven,
        "time_unknown": chart.time_unknown,
    }

    user_tier = user.tier if user else "free"
    interp_request = InterpretationRequest(natal_profile=profile, tier=user_tier)
    router = get_router()

    async def event_stream():
        # Сохранённый разбор: одно событие с текстом и [DONE]. Формат тот
        # же, что у живого стрима — клиент (_connectSSE в api/client.js)
        # копит текст в буфер и сбрасывает его по [DONE], ему безразлично,
        # пришёл текст одним куском или сотней. Разница только визуальная:
        # набор не анимируется, разбор появляется целиком.
        if saved_interpretation is not None:
            payload = {'text': saved_interpretation.content}
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            # Запись в БД делает _save_chart_interpretation, и только после
            # успешно завершённого цикла, то есть при finish_reason == "stop".
            # Значит для сохранённого текста "stop" — факт о нём, а не догадка.
            yield _finish_event("stop")
            yield "data: [DONE]\n\n"
            return

        # Отказ по лимиту: единственное событие и выход. Ни [DONE] (клиент
        # счёл бы это успехом), ни обращений к БД, ни расхода — до цикла не
        # доходим, produced остаётся False.
        if limit_error is not None:
            yield f"data: {json.dumps({'error': limit_error}, ensure_ascii=False)}\n\n"
            return

        produced = False
        collected: list[str] = []
        try:
            async for chunk in router.stream(interp_request):
                produced = True
                collected.append(chunk)
                # SSE format: data: <content>\n\n
                yield f"data: {json.dumps({'text': chunk}, ensure_ascii=False)}\n\n"
            # Расход фиксируем только при реально выданном полном контенте
            if produced:
                _save_chart_interpretation(db, chart, profile, collected, interp_request)
                tier_limiter.commit_interpretation(user, db, chart=chart)
            yield _finish_event(getattr(interp_request, "finish_reason", None))
            yield "data: [DONE]\n\n"
        except IncompleteInterpretation:
            # Обрезано по длине или связь оборвалась после части текста —
            # не [DONE], не засчитываем попытку (см. router.stream()).
            logger.warning("Interpretation stream incomplete for chart=%s", chart_id)
            yield f"data: {json.dumps({'error': 'Не удалось получить полный текст разбора. Попробуй ещё раз.'})}\n\n"
        except Exception as e:
            logger.exception("Streaming interpretation failed")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post(
    "/api/v1/chart/{chart_id}/interpret",
    tags=["interpretation"],
    summary="Generate full interpretation (non-streaming)",
)
@limiter.limit(settings.rate_limit_anon)
async def interpret_chart_full(
    request: Request,
    chart_id: str,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    """Generate a complete AI interpretation of a natal chart.

    Returns the full text at once (no streaming).
    """
    from backend.interpretation.base import InterpretationRequest
    from backend.interpretation.router import get_router

    # Как и в потоковом близнеце выше: карту получаем ДО проверки лимита —
    # с 048 бесплатный разбор Free считается по карте. Здесь, в отличие от SSE,
    # отказ остаётся обычным HTTP 403: этот эндпоинт не потоковый, ответ
    # доезжает до клиента целиком и читается через ApiError.
    chart = resolve_chart_access(chart_id, user, chart_token(request), db)
    tier_limiter.check_interpretation_limit(user, db, chart=chart)

    profile = {
        "planets": chart.planets,
        "houses": chart.houses,
        "aspects": chart.aspects,
        "ascendant": chart.ascendant,
        "midheaven": chart.midheaven,
        "time_unknown": chart.time_unknown,
    }

    user_tier = user.tier if user else "free"
    interp_request = InterpretationRequest(natal_profile=profile, tier=user_tier)
    router = get_router()
    result = await router.generate(interp_request)

    # Успешную генерацию (не сервис-заглушку) фиксируем в счётчик
    if result and result.engine not in ("none",):
        tier_limiter.commit_interpretation(user, db, chart=chart)

    return {
        "chart_id": chart_id,
        "content": result.content,
        "sections": result.sections,
        "engine": result.engine,
        "cached": result.cached,
    }


@app.get("/health/ai", tags=["health"], summary="AI providers health")
async def health_ai():
    """Check availability of all AI providers and infrastructure services.
    
    Returns:
        - status: "ok" | "degraded" | "down"
        - services: detailed status for OpenAI, DeepSeek, Redis, PostgreSQL
    """
    from backend.health import check_all_services
    return await check_all_services()


# ═══════════════════════════════════════════════════════════
# TRANSIT ENDPOINTS (Phase 3)
# ═══════════════════════════════════════════════════════════

@app.get(
    "/api/v1/chart/{chart_id}/transits",
    response_model=TransitResponse,
    responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    tags=["transits"],
    summary="Calculate transits for a period",
)
@limiter.limit(settings.rate_limit_anon)
async def get_transits(
    request: Request,
    chart_id: str,
    from_date: str,
    to_date: str,
    planet: str | None = None,
    max_orb: float | None = None,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    """Calculate transit aspects to a natal chart for a given date range.

    Query params:
      - from_date: start date (YYYY-MM-DD)
      - to_date: end date (YYYY-MM-DD)
      - planet: (optional) filter by transit planet name
      - max_orb: (optional) max orb in degrees (default: standard transit orbs)

    Returns array of transit events sorted by date.
    """
    # E2: список транзитов виден всем тарифам (Free — с блюром AI-разбора на клиенте).
    from datetime import date as date_type
    from backend.transit.engine import window_events
    from backend.cache import transit_cache, make_profile_hash

    # 1. Load natal chart
    chart = resolve_chart_access(chart_id, user, chart_token(request), db)

    # 2. Parse and validate dates
    try:
        from_dt = date_type.fromisoformat(from_date)
        to_dt = date_type.fromisoformat(to_date)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail="Invalid date format. Use YYYY-MM-DD.",
        )

    if to_dt <= from_dt:
        raise HTTPException(status_code=422, detail="to_date must be after from_date.")

    delta = (to_dt - from_dt).days
    if delta > 366:
        raise HTTPException(
            status_code=422,
            detail="Transit period cannot exceed 1 year (366 days).",
        )

    # 2b. Тарифный горизонт. До 31.08.2026 диапазон не проверялся вовсе:
    # transits_months жил только в TIER_FLAGS и в арифметике фронтенда, а
    # check_transit_access (auth/rate_limits.py) была написана и не вызывалась
    # ни разу — то есть горизонт держался исключительно на клиенте, и прямой
    # запрос отдавал Веге хоть 24 месяца.
    #
    # ⚠️ check_transit_access здесь НАМЕРЕННО не подключена. Она отдаёт 403
    # при transits_months == 0, то есть закрыла бы free сам СПИСОК транзитов,
    # а решение E2 — ровно обратное: список виден всем, монетизируется
    # AI-разбор. Её 403 снёс бы витрину free вместе с FreePlanBanner и
    # PlanComparisonModal. Гейтим горизонт, а не факт доступа.
    # (С 08.09.2026 у free transits_months = 3, и та функция не выстрелила бы
    # даже будучи подключённой — но подключать её всё равно не следует: её
    # смысл «тариф без транзитов», а такого тарифа в сетке нет.)
    _tier = user.tier if user else "free"
    # «Сегодня» — местное (user_tz), как у таймлайна; запас в сутки внутри
    # transits_date_window остаётся — пояс браузера может отличаться от
    # сохранённого пояса устройства.
    _win_from, _win_to = transits_date_window(_tier, local_today(user_tz(None, user, chart)))
    if from_dt < _win_from or to_dt > _win_to:
        raise HTTPException(
            status_code=403,
            detail=(
                f"Запрошенный период вне горизонта тарифа. "
                f"Доступно с {_win_from.isoformat()} по {_win_to.isoformat()}."
            ),
        )

    # 3. Check cache
    # v4 (04.10.2026, шаг 3): без времени рождения — без натальной Луны.
    # v5 (05.10.2026): без событий без касания (TransitEvent.no_touch).
    cache_key = f"transit:v5:{chart_id}:{from_date}:{to_date}:{planet}:{max_orb}"
    cached = transit_cache.get(cache_key)
    if cached:
        logger.info("Transit cache hit: %s", cache_key[:40])
        return TransitResponse(
            chart_id=chart_id,
            from_date=from_date,
            to_date=to_date,
            events=[TransitEventSchema(**e) for e in cached],
        )

    # 4. Calculate transits — engine.window_events: та же функция у прогона
    # согласованности (cB, /transits), чтобы он проверял ровно ответ веба.
    planet_filter = [planet] if planet else None

    try:
        # to_thread: расчёт транзитов на год — CPU-bound синхронный код на
        # 1–4 секунды (замерено: 3 мес ≈ 1 с, 12 мес ≈ 4 с). Без него один
        # такой запрос блокирует единственный event loop процесса целиком —
        # встают чужие SSE-стримы и даже /health. to_thread отпускает GIL на
        # время вызова расширения pyswisseph, так что параллелизм настоящий,
        # а не мнимый.
        events = await asyncio.to_thread(
            window_events, chart, from_dt, to_dt, orb_filter=max_orb, planet_filter=planet_filter,
        )
    except Exception as e:
        logger.exception("Transit calculation failed")
        raise HTTPException(status_code=500, detail=f"Transit calculation error: {e}")

    # Письмо «Важный транзит» отсюда больше не уходит (до 05.10.2026 —
    # только если человек открыл транзиты на вебе): его шлёт ежечасный прогон
    # писем, lifecycle_emails._send_transit_alerts.

    # 5. Build response
    events_resp = [TransitEventSchema(**e) for e in events]

    # 6. Cache result (7 days TTL)
    transit_cache.set(
        cache_key,
        [e.model_dump() for e in events_resp],
        ttl=7 * 24 * 3600,
    )

    return TransitResponse(
        chart_id=chart_id,
        from_date=from_date,
        to_date=to_date,
        events=events_resp,
    )



@app.get(
    "/api/v1/chart/{chart_id}/transits/positions",
    tags=["transits"],
    summary="Current transit planet positions for a given date",
)
async def get_transit_positions(
    request: Request,
    chart_id: str,
    on_date: str,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    """Return ecliptic longitudes of all transit planets for the given date.

    Used by the frontend to render transit planets on the natal wheel.
    chart_id is validated but positions are date-only (no chart dependency).
    """
    from datetime import date as date_type
    from backend.transit.engine import get_planet_positions_for_date

    chart = resolve_chart_access(chart_id, user, chart_token(request), db)

    try:
        query_date = date_type.fromisoformat(on_date)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid date format. Use YYYY-MM-DD.")

    planets = get_planet_positions_for_date(query_date)
    return {"date": on_date, "planets": planets}


@app.get(
    "/api/v1/chart/{chart_id}/transits/interpret",
    tags=["transits"],
    summary="Stream transit period interpretation (SSE)",
)
@limiter.limit(settings.rate_limit_anon)
async def interpret_transits(
    request: Request,
    chart_id: str,
    from_date: str,
    to_date: str,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    """Stream an AI interpretation of all transits for a period.

    First calculates transits, then generates an overview interpretation
    via the AI fallback chain (GPT-4o → DeepSeek → templates).
    """
    from datetime import date as date_type
    from backend.transit.engine import calculate_transits, get_transit_summary
    from backend.transit.prompts import build_transit_period_prompt, get_template_transit_text
    from backend.interpretation.base import InterpretationRequest
    from backend.interpretation.router import get_router

    chart = resolve_chart_access(chart_id, user, chart_token(request), db)

    # Тот же приём, что в /chart/{id}/interpret: отказ по лимиту уезжает первым
    # событием в потоке, а не HTTP-статусом. Эндпоинт читается через EventSource
    # (streamTransitInterpretation → _connectSSE в api/client.js), а тот не даёт
    # JS доступа ни к коду ответа, ни к телу — прежний 403 до открытия
    # StreamingResponse означал, что текст «AI-расшифровка транзитов доступна на
    # Лире и выше» до пользователя не доезжал: после трёх реконнектов он видел
    # «Соединение прервалось».
    #
    # Проверка переехала ПОСЛЕ resolve_chart_access — как и в интерпретации
    # карты: отложенный отказ означает, что выполнение продолжается, и порядок
    # «сначала доступ, потом лимит» надо задать явно. Следствие: чужая или
    # несуществующая карта отвечает 404 раньше, чем сработает лимит.
    #
    # Аноним — исключение, ему по-прежнему настоящий 403.
    limit_error: str | None = None
    try:
        tier_limiter.check_transit_ai_limit(user, db)
    except HTTPException as exc:
        if user is None or not isinstance(exc.detail, str):
            raise
        limit_error = exc.detail

    # Parse dates
    try:
        from_dt = date_type.fromisoformat(from_date)
        to_dt = date_type.fromisoformat(to_date)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid date format.")

    # Calculate transits
    events = await asyncio.to_thread(
        calculate_transits,
        natal_planets=natal_planets(chart),   # без времени рождения — без Луны
        from_date=from_dt,
        to_date=to_dt,
    )

    events = [e for e in events if not e.no_touch]   # без касания — как в /transits

    # Build natal profile
    profile = {
        "planets": chart.planets,
        "houses": chart.houses,
        "aspects": chart.aspects,
        "ascendant": chart.ascendant,
        "midheaven": chart.midheaven,
        "time_unknown": chart.time_unknown,
    }

    # Build transit events as dicts for prompt
    transit_dicts = [
        {
            "date": e.date,
            "transit_planet": e.transit_planet,
            "transit_sign": e.transit_sign,
            "natal_planet": e.natal_planet,
            "aspect_type": e.aspect_type,
            "orb": e.orb,
            "exact_date": e.exact_date,
        }
        for e in events
    ]

    # Try AI interpretation, fall back to template summary
    router = get_router()

    async def event_stream():
        # Отказ по лимиту: единственное событие и выход. Ни [DONE] (клиент
        # счёл бы это успехом), ни расхода — commit_transit_ai ниже стоит внутри
        # ветки успешного стрима, до неё не доходим.
        if limit_error is not None:
            yield f"data: {json.dumps({'error': limit_error}, ensure_ascii=False)}\n\n"
            return

        try:
            # Build a custom request with transit context
            period_prompt = build_transit_period_prompt(
                transit_events=transit_dicts,
                natal_profile=profile,
                from_date=from_date,
                to_date=to_date,
            )

            interp_request = InterpretationRequest(
                natal_profile=profile,
                context="transit",
                tier=user.tier if user else "free",
                custom_prompt=period_prompt,
            )

            # Try streaming from AI engines (skip template — handled below)
            for eng in router._engines:
                if eng.name == "template":
                    continue
                if not router._check_budget(eng.name):
                    continue
                try:
                    streamed = False
                    collected: list[str] = []   # для детектора родовых форм
                    async for chunk in eng.stream(interp_request):
                        collected.append(chunk)
                        yield f"data: {json.dumps({'text': chunk}, ensure_ascii=False)}\n\n"
                        streamed = True
                    if streamed:
                        # Ключ расхода — eng.name, тот же, по которому выше
                        # спрашивали _check_budget. Токены из движка, не оценка.
                        router._track_spend(
                            eng.name, getattr(eng, "_last_stream_tokens", 0) or 0
                        )
                        # Списываем AI-транзит только при реальной работе AI-движка (Lite-квота)
                        tier_limiter.commit_transit_ai(user, db)
                        from backend.interpretation.gender_check import report as _gender_report
                        _gender_report("".join(collected), "transit")
                        yield "data: [DONE]\n\n"
                        return
                except Exception as e:
                    logger.warning("Transit stream from %s failed: %s", eng.name, e)
                    continue

            # Template fallback: generate summary from templates
            summary = get_transit_summary(events)
            text_parts = [f"### Обзор транзитов: {from_date} — {to_date}\n\n"]
            text_parts.append(
                f"За этот период обнаружено **{summary['total_events']}** "
                f"значимых транзитных аспектов.\n\n"
            )

            if summary["significant"]:
                text_parts.append("### Ключевые транзиты периода\n\n")
                for sig in summary["significant"]:
                    template_text = get_template_transit_text(
                        sig["description"].split()[0],  # transit planet
                        sig["description"].split()[-1],  # natal planet
                        sig["description"].split()[1],   # aspect
                    )
                    text_parts.append(
                        f"**{sig['date']}** — {sig['description']} "
                        f"(орб: {sig['orb']}°)\n\n{template_text}\n\n"
                    )

            full_text = "".join(text_parts)
            # Stream in paragraphs
            for para in full_text.split("\n\n"):
                if para.strip():
                    yield f"data: {json.dumps({'text': para + chr(10) + chr(10)}, ensure_ascii=False)}\n\n"

            yield "data: [DONE]\n\n"

        except Exception as e:
            logger.exception("Transit interpretation stream failed")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post(
    "/api/v1/chart/{chart_id}/transits/event/interpret",
    tags=["transits"],
    summary="Interpret a single transit event (SSE)",
)
@limiter.limit(settings.rate_limit_anon)
async def interpret_transit_event(
    request: Request,
    chart_id: str,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    """Stream AI interpretation of a single transit event.

    Request body: transit event identifier (from /transits response) —
    used only to look up WHICH transit this is; знак/градус/дом/орб/даты
    пересчитываются на бэкенде (compute_exact_facts), клиентским значениям
    не доверяем.
    """
    _tier = user.tier if user else "free"
    if _tier != "free":
        tier_limiter.check_transit_ai_limit(user, db)
    else:
        # Free: 2 пробных разбора на всё время, на любые транзиты (решение
        # владельца 28.09.2026). Проверки «значимый» больше нет.
        tier_limiter.check_transit_trial(user, db)
    from backend.transit.prompts import (
        TRANSIT_PROMPT_VERSION,
        TRANSIT_PROMPT_VERSION_SKY,
        build_transit_event_prompt,
        get_template_transit_text,
    )
    from backend.interpretation.base import InterpretationRequest
    from backend.interpretation.router import get_router
    from backend.transit.engine import compute_exact_facts
    from backend.cache import transit_interp_cache
    from datetime import date as _date

    chart = resolve_chart_access(chart_id, user, chart_token(request), db)

    # Parse transit event identifier from request body
    body = await request.json()
    transit_planet = body.get("transit_planet", "")
    natal_planet = body.get("natal_planet", "")
    aspect_type = body.get("aspect_type", "")

    if not all([transit_planet, natal_planet, aspect_type]):
        raise HTTPException(
            status_code=422,
            detail="Required fields: transit_planet, natal_planet, aspect_type",
        )

    _ref_date_str = (body.get("peak_date") or body.get("date") or "")[:10]
    if not _ref_date_str:
        raise HTTPException(status_code=422, detail="Required field: peak_date (or date)")

    # Без времени рождения — без натальной Луны, углов и полуденных домов
    # (chart_points, шаг 3 аудита): иначе compute_exact_facts назвал бы дом
    # транзита и натальной точки по куспидам на полдень.
    unknown = bool(chart.time_unknown)
    if unknown and natal_planet in UNKNOWN_TIME_HIDDEN:
        raise HTTPException(status_code=422, detail="Без времени рождения эта точка карты не определена.")
    profile = {
        "planets": natal_planets(chart),
        "houses": [] if unknown else chart.houses,
        "aspects": chart.aspects,
        "ascendant": {} if unknown else chart.ascendant,
        "midheaven": {} if unknown else chart.midheaven,
        "time_unknown": chart.time_unknown,
    }

    # Ключ однозначно определяет событие: одна и та же пара планета/аспект
    # повторяется из года в год (Марс к Солнцу — раз в ~2 года), поэтому
    # peak_date в ключе обязателен — иначе разборы разных лет склеятся.
    cache_key = f"transit_interp:v{TRANSIT_PROMPT_VERSION}:{chart_id}:{transit_planet}:{natal_planet}:{aspect_type}:{_ref_date_str}"

    # Под флагом sky_event (задание 4.5) — событие ядра: один разбор на всё
    # событие (О5), ключ — `ev.key` вместо даты карточки, поэтому все карточки
    # касаний петли открывают один текст и квоту списывают один раз. Пояс — в
    # ключе: даты в фактах местные. События у ядра нет (веб прислал дату без
    # касания и без прохода) — старый путь.
    from backend import day_event
    from backend.transit.engine import interpret_event_facts
    sky_tz = user_tz(body.get("tz"), user, chart)
    sky_facts, sky_key = await asyncio.to_thread(
        interpret_event_facts, chart, transit_planet, natal_planet, aspect_type,
        _date.fromisoformat(_ref_date_str), sky_tz, day_event._sky_on(chart))
    if sky_key is not None:
        cache_key = f"transit_interp:v{TRANSIT_PROMPT_VERSION_SKY}:{chart_id}:{sky_key}:{sky_tz}"

    async def _yield_chunked(text: str):
        """Отдаём готовый текст тем же SSE-форматом, что и живой стрим —
        фронт не отличает кэш-хит от генерации.

        Нарезка общая с интерпретацией натальной карты
        (async_utils.replay_as_stream); здесь остаётся только обрамление в
        SSE-кадры, потому что у второго вызывающего оно своё.
        """
        async for piece in replay_as_stream(text):
            yield f"data: {json.dumps({'text': piece}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    cached = transit_interp_cache.get(cache_key)
    if cached:
        logger.info("Transit interp cache HIT key=%s engine=%s", cache_key, cached.get("engine"))

        async def event_stream_cached():
            # Кэш-хит не расходует квоту: модель не вызывается, платить не за
            # что. Ключ кэша без user_id и держится 30 суток — без этой
            # оговорки повторное открытие того же транзита в пределах месяца
            # списывало бы у Веги единицу из трёх ни за что. Списание живёт
            # только на пути реальной генерации, ниже.
            async for chunk in _yield_chunked(cached["content"]):
                yield chunk

        return StreamingResponse(
            event_stream_cached(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )

    logger.info("Transit interp cache MISS key=%s", cache_key)

    # Swiss Ephemeris — синхронный, блокирует event loop (см. CLAUDE.md).
    # Натальная точка — из day_event.points, как в ленте: в natal_planets
    # углов нет, и до 05.10.2026 разбор касания к ASC/MC шёл без знака,
    # градуса и дат (аудит 8.1). Без времени рождения углов нет и там.
    from backend.day_event import points as day_points
    if sky_facts is not None:
        facts = sky_facts
    else:
        facts = await asyncio.to_thread(
            compute_exact_facts,
            transit_planet, natal_planet, aspect_type, _date.fromisoformat(_ref_date_str),
            {**profile, "planets": day_points(chart)},
        )
    transit_event_dict = {
        "transit_planet": transit_planet,
        "natal_planet": natal_planet,
        "aspect_type": aspect_type,
        **facts,
    }

    event_prompt = build_transit_event_prompt(
        transit_event=transit_event_dict,
        natal_profile=profile,
        language=body.get("language", "ru"),
    )

    router = get_router()

    async def event_stream():
        collected: list[str] = []
        try:
            interp_request = InterpretationRequest(
                natal_profile=profile,
                context="transit",
                tier=user.tier if user else "free",
                custom_prompt=event_prompt,
            )

            for eng in router._engines:
                if eng.name == "template":
                    continue
                if not router._check_budget(eng.name):
                    continue
                try:
                    streamed = False
                    async for chunk in eng.stream(interp_request):
                        collected.append(chunk)
                        yield f"data: {json.dumps({'text': chunk}, ensure_ascii=False)}\n\n"
                        streamed = True
                    if streamed:
                        router._track_spend(
                            eng.name, getattr(eng, "_last_stream_tokens", 0) or 0
                        )
                        transit_interp_cache.set(
                            cache_key,
                            {"content": "".join(collected), "engine": eng.name},
                        )
                        tier_limiter.commit_transit_ai(user, db)
                        from backend.interpretation.gender_check import report as _gender_report
                        _gender_report("".join(collected), "transit")
                        yield "data: [DONE]\n\n"
                        return
                except Exception as e:
                    logger.error("Transit event stream from %s failed: %s", eng.name, e)
                    collected.clear()
                    continue

            # Template fallback — не кэшируем (не AI-разбор конкретным движком)
            text = get_template_transit_text(transit_planet, natal_planet, aspect_type)
            yield f"data: {json.dumps({'text': text}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

        except Exception as e:
            logger.exception("Transit event interpretation failed")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── Planner: monthly (no AI) ──────────────────────────────────────────────────
@app.get(
    "/api/v1/chart/{chart_id}/planner/monthly",
    tags=["planner"],
    summary="Monthly planner without AI — pure Python interpretation",
)
@limiter.limit(settings.rate_limit_anon)
async def get_monthly_planner(
    request: Request,
    chart_id: str,
    month_offset: int = 0,
    week_offset: int | None = None,
    tz: str | None = None,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    import calendar as cal_mod
    from datetime import date as date_type
    from backend.transit.planner_engine import build_planner

    chart = resolve_chart_access(chart_id, user, chart_token(request), db)

    _uid = user.id if user else None
    log_event(db, _uid, EventName.TIMELINE_OPEN, {"chart_id": chart_id})
    maybe_mark_second_visit(db, _uid)

    if chart.time_unknown:
        return {"planner": {"error": "Время рождения неизвестно — планер недоступен."}}

    # Тарифный горизонт планера. До 31.08.2026 month_offset не проверялся
    # ничем: planner_months жил в TIER_FLAGS, но на бэкенде не читался нигде,
    # а во фронтенде использовался только для подписи в профиле. Ограничение
    # держалось на одной строке PlannerPage.jsx (`if (isPro && monthOffset)`),
    # то есть прямой запрос отдавал Веге планер на год вперёд.
    #
    # Гейт КОНТЕНТА внутри build_planner (locked/_locked_payload) работает
    # верно и здесь не дублируется: он решает, что показать в месяце, а эта
    # проверка — какой месяц вообще можно запросить.
    _p_min, _p_max = planner_offset_window(user.tier if user else "free")
    if not (_p_min <= month_offset <= _p_max):
        raise HTTPException(
            status_code=403,
            detail=(
                f"Планер доступен на {_p_max} мес. вперёд на твоём тарифе "
                f"(запрошено {month_offset})."
            ),
        )

    # today и время проходов — в поясе человека (time_utils.user_tz: tz
    # запроса → устройство → карта → Москва; шаг 2 аудита, 04.10.2026).
    _tz = user_tz(tz, user, chart)
    today = local_today(_tz)

    # Сдвигаем на month_offset месяцев
    target_year = today.year + (today.month - 1 + month_offset) // 12
    target_month = (today.month - 1 + month_offset) % 12 + 1
    last_day = cal_mod.monthrange(target_year, target_month)[1]
    month_start = date_type(target_year, target_month, 1)
    month_end = date_type(target_year, target_month, last_day)

    natal_profile = {
        "planets":   chart.planets,
        "houses":    chart.houses,
        "ascendant": chart.ascendant,
        "midheaven": chart.midheaven,
    }

    # build_planner считает через Swiss Ephemeris (дома/ретрограды) —
    # синхронный, блокирует event loop (см. CLAUDE.md).
    planner = await asyncio.to_thread(
        build_planner,
        natal_profile=natal_profile,
        from_date=month_start,
        to_date=month_end,
        today=today,
        user_timezone=_tz,
        tier=(user.tier if user else "free"),
        week_offset=week_offset,
        with_upcoming=(month_offset == 0),
    )

    return {"planner": planner}



# ═══════════════════════════════════════════════════════════
# ASYNC TASK ENDPOINTS (Celery)
# ═══════════════════════════════════════════════════════════

class PdfRequest(BaseModel):
    wheel_png: str | None = None  # base64 PNG колеса, опционально


@app.post(
    "/api/v1/chart/{chart_id}/pdf",
    tags=["chart"],
    summary="Generate PDF report and return bytes directly",
)
@limiter.limit(settings.rate_limit_anon)
async def start_pdf_generation(
    request: Request,
    chart_id: str,
    pdf_body: PdfRequest | None = None,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    from fastapi.responses import Response as FastResponse
    import asyncio

    if chart_id == "anonymous":
        raise HTTPException(
            status_code=400,
            detail="Сохрани карту перед скачиванием PDF. Войди или зарегистрируйся."
        )

    chart = resolve_chart_access(chart_id, user, chart_token(request), db)

    # BOLA: только владелец (или анонимная карта)
    from backend.authz import assert_chart_access
    assert_chart_access(chart, user)

    # Тарифный гейт самого PDF. До 30.08.2026 его здесь не было вовсе:
    # проверялся только доступ к карте, и бесплатный пользователь получал
    # платный пункт сетки в любом количестве.
    tier_limiter.check_pdf_limit(user, db)

    # Load interpretation from DB
    from backend.models import Interpretation
    interp_row = (
        db.query(Interpretation)
        .filter(Interpretation.chart_id == chart_id)
        .order_by(Interpretation.created_at.desc())
        .first()
    )

    interpretation_text = ""
    if interp_row:
        interpretation_text = interp_row.content
    else:
        # Генерация на лету остаётся: платный пользователь может нажать
        # «Скачать PDF», не открыв разбор, и отказ в этом случае был бы
        # регрессом. Но идти она обязана через лимитер — иначе это второй
        # бесплатный путь к AI-разбору мимо квоты.
        #
        # Проверка стоит СНАРУЖИ try: внутри её HTTPException проглотил бы
        # `except Exception` ниже, и отказ превратился бы в тихую выдачу PDF
        # без разбора.
        #
        # Текст отказа переформулируется под этот путь. Общий текст гейта
        # («Лимит N интерпретаций в месяц исчерпан…») здесь дезориентирует:
        # человек нажимал «Скачать PDF» и про интерпретации не спрашивал —
        # решит, что сломалось. Сам гейт не трогаем, у него ещё три
        # вызывающих, где его формулировка верна.
        #
        # Статус сохраняется тот, что поднял гейт: 429 при исчерпанной квоте,
        # 403 на прочих ветвях (сейчас недостижимых — check_pdf_limit отбивает
        # free раньше).
        try:
            tier_limiter.check_interpretation_limit(user, db, chart=chart)
        except HTTPException as limit_exc:
            from backend.email_service import TIER_NAMES
            tier_name = (
                TIER_NAMES.get(user.tier, user.tier.capitalize())
                if user else TIER_NAMES["free"]
            )
            raise HTTPException(
                status_code=limit_exc.status_code,
                detail=(
                    "PDF собирается вместе с разбором карты, а лимит разборов "
                    f"в этом месяце исчерпан на тарифе {tier_name}. "
                    "PDF по картам, где разбор уже есть, работает как обычно."
                ),
            ) from limit_exc

        # Generate on-the-fly
        try:
            from backend.interpretation.base import InterpretationRequest
            from backend.interpretation.router import get_router
            profile = {
                "planets": chart.planets, "houses": chart.houses, "aspects": chart.aspects,
                "ascendant": chart.ascendant, "midheaven": chart.midheaven,
                "time_unknown": chart.time_unknown,
            }
            # tier передаётся явно: без него глубина бралась дефолтная, то есть
            # платный пользователь получал через PDF не тот объём, за который
            # заплатил (interpretation_word_limit — тарифный).
            interp_req = InterpretationRequest(
                natal_profile=profile,
                tier=user.tier if user else "free",
            )
            ai_router = get_router()
            result = await ai_router.generate(interp_req)
            interpretation_text = result.content or ""
            # Save for next time
            if interpretation_text:
                from backend.cache import make_profile_hash
                db.add(Interpretation(
                    chart_id=chart_id,
                    profile_hash=make_profile_hash(profile),
                    engine=result.engine or "pdf",
                    content=interpretation_text,
                    sections=result.sections,
                    tier=interp_req.tier,
                ))
                db.commit()
                # Расход списывается только при реально выданном тексте и
                # только здесь — на ветке с готовой строкой в Interpretation
                # генерации не было, списывать нечего.
                tier_limiter.commit_interpretation(user, db, chart=chart)
        except Exception as exc:
            logger.exception("PDF: failed to get interpretation: %s", exc)

    # Astrologer branding
    astrologer_name = None
    if user:
        try:
            from backend.models import AstrologerProfile
            if hasattr(user, "tier") and user.tier == "premium":
                profile_obj = db.query(AstrologerProfile).filter(
                    AstrologerProfile.user_id == user.id
                ).first()
                if profile_obj and profile_obj.display_name:
                    astrologer_name = profile_obj.display_name
        except Exception:
            pass

    from backend.natal_pdf import generate_pdf_bytes
    wheel_png = pdf_body.wheel_png if pdf_body else None
    pdf_bytes = generate_pdf_bytes(
        chart,
        interpretation=interpretation_text,
        astrologer_name=astrologer_name,
        wheel_png=wheel_png,
    )

    # Списываем PDF только после реально собранного файла: если
    # generate_pdf_bytes упадёт, исключение уйдёт наверх и квота не сгорит.
    tier_limiter.commit_pdf(user, db)

    filename = f"natal_chart_{chart_id[:8]}.pdf"
    return FastResponse(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@debug_router.get('/api/v1/debug/moon')
async def debug_moon():
    import swisseph as swe, os
    ephe_path = os.getenv('EPHE_PATH', 'data/ephe')
    swe.set_ephe_path(ephe_path)

    def _moon_angle(jd):
        sun, _ = swe.calc_ut(jd, swe.SUN, swe.FLG_SWIEPH)
        moon, _ = swe.calc_ut(jd, swe.MOON, swe.FLG_SWIEPH)
        return (moon[0] - sun[0]) % 360

    # Проверим значения угла вокруг 1 мая и 16 мая
    checks = []
    for label, y, mo, d, h in [
        ("30apr_17utc", 2026, 4, 30, 17.0),
        ("01may_00utc", 2026, 5, 1, 0.0),
        ("15may_20utc", 2026, 5, 15, 20.0),
        ("16may_06utc", 2026, 5, 16, 6.0),
        ("30may_08utc", 2026, 5, 30, 8.0),
        ("31may_08utc", 2026, 5, 31, 8.0),
    ]:
        jd = swe.julday(y, mo, d, h)
        angle = _moon_angle(jd)
        checks.append({"label": label, "angle": round(angle, 2)})

    return {"checks": checks}


# ═══════════════════════════════════════════════════════════
# GENERAL CALENDAR — бесплатный, без натальной карты
# ═══════════════════════════════════════════════════════════

@app.get(
    "/api/v1/calendar/monthly",
    tags=["calendar"],
    summary="General astro calendar for a month (free tier)",
)
@limiter.limit(settings.rate_limit_anon)
async def get_general_calendar(
    request: Request,
    month: str,           # формат: "2025-12"
):
    """Общий астро-календарь — новолуния, полнолуния, ингрессы, аспекты (UTC).
    Не требует натальной карты. Бесплатный уровень.

    `overview` — знаки новолуния и полнолуния месяца. До 04.10.2026 их
    «писала» модель (Claude Sonnet), повторяя знаки из уже посчитанных
    событий, — единственное, что веб брал из её ответа. Шаг 6 аудита: знаки
    считает код, вызова модели нет, бюджет не тратится. Веб показывает их
    только запасным вариантом, если /calendar/lunar не ответил.
    """
    try:
        year, mon = map(int, month.split("-"))
    except ValueError:
        raise HTTPException(status_code=422, detail="Формат: YYYY-MM (напр. 2025-12)")

    # Ответ зависит только от YYYY-MM и одинаков для всех. Кэш — ради тяжёлого
    # скана ингрессов и аспектов; `code1` в ключе — ответы, собранные моделью
    # (`general_calendar:v8:…`), не переиспользуются.
    calendar_cache_key = f"general_calendar:code1:{year:04d}-{mon:02d}"
    cached_calendar = interpretation_cache.get(calendar_cache_key)
    if cached_calendar is not None:
        return cached_calendar

    # Swiss Ephemeris — синхронно (см. CLAUDE.md)
    key_events = await asyncio.to_thread(get_monthly_calendar, year, mon)
    first = lambda t: next(({"sign": e["sign"]} for e in key_events if e["type"] == t), None)
    result = {
        "month": month,
        "events": key_events,
        "overview": {"new_moon": first("new_moon"), "full_moon": first("full_moon")},
    }
    interpretation_cache.set(calendar_cache_key, result, ttl=86400)
    return result


# ═══════════════════════════════════════════════════════════
# LUNAR CALENDAR
# ═══════════════════════════════════════════════════════════

def _compute_lunar_calendar(year: int, month: int, tz: str) -> dict:
    """Фазы, затмения, равноденствия и знак Луны на каждый день месяца в поясе
    `tz` — тяжёлый синхронный расчёт через Swiss Ephemeris. Вызывать только
    через asyncio.to_thread (см. CLAUDE.md) — не напрямую из async-хендлера.

    Шаг 6 аудита (04.10.2026): до него здесь был свой цикл бисекции фаз и
    сетка GMT+3 для всех — во Владивостоке новолуние 10.10.2026 18:50 МСК
    стояло на 10.10, а в ленте на 11.10. Теперь фазы — lunations (одна функция
    на проект), даты и время — местные, пояс отдаётся полем `tz`.
    """
    from datetime import date as date_type, datetime as dt_type, time as time_type
    from zoneinfo import ZoneInfo
    from backend.calendar.lunar_engine import (
        get_eclipses, get_solar_events, lunations_local, sign_in, ZODIAC_SIGNS, _jd_at, _lon,
    )
    import calendar as cal_mod

    zone = ZoneInfo(tz)
    _, days_in_month = cal_mod.monthrange(year, month)
    first, last = date_type(year, month, 1), date_type(year, month, days_in_month)
    phases = []
    for ln in lunations_local(first, last, tz):
        loc = ln.local(zone)
        label = "Новолуние" if ln.type == "new_moon" else "Полнолуние"
        phases.append({
            "date": loc.date().isoformat(),
            "time": f"{loc:%H:%M}",
            "type": ln.type, "planet": "Moon",
            "sign": ln.sign, "emoji": "🌑" if ln.type == "new_moon" else "🌕",
            "description": f"{label} {sign_in(ln.sign)}",
        })

    eclipses = get_eclipses(first, last, tz)
    # Равноденствия и солнцестояния: обычно пустой список — их четыре в году.
    # Считаются там же, где затмения, и отдаются отдельным ключом, а не внутри
    # phases: phases — это ровно две повторяющиеся фазы Луны, и фронт фильтрует
    # их по type. Своё поле повторяет устройство eclipses, а не ломает phases.
    solar_events = get_solar_events(year, month, tz)
    # Знак дня — в МЕСТНЫЙ полдень, как в прогнозе дня (до 04.10.2026 — 12:00 UTC).
    # `phase` и `elong` — те же, что у виджета (story_card): приложение кладёт
    # их виджету, и Moon.java (средний месяц, ошибка до полусуток) считает
    # только без них — шаг 6 аудита.
    from backend import story_card
    daily_signs = []
    for day in range(1, days_in_month + 1):
        d = date_type(year, month, day)
        lon = _lon(_jd_at(dt_type.combine(d, time_type(12), zone)), "Moon")
        daily_signs.append({
            "date": d.isoformat(),
            "sign": ZODIAC_SIGNS[int(lon // 30) % 12],
            "longitude": round(lon, 2),
            "phase": story_card.moon_phase(d, tz),
            "elong": round(story_card.elongation(d, tz), 1),
        })

    lon_now = _lon(_jd_at(dt_type.now(zone)), "Moon")

    return {
        "year":  year,
        "month": month,
        "tz":    tz,
        "current_moon": {
            "sign":   ZODIAC_SIGNS[int(lon_now // 30) % 12],
            "degree": round(lon_now % 30, 1),
        },
        "phases":       phases,
        "daily_signs":  daily_signs,
        "eclipses":     eclipses,
        "solar_events": solar_events,
    }


@app.get(
    "/api/v1/calendar/lunar",
    tags=["calendar"],
    summary="Lunar calendar: moon phases + moon sign per day",
)
@limiter.limit(settings.rate_limit_anon)
async def get_lunar_calendar(
    request: Request,
    year: int = None,
    month: int = None,
    tz: str | None = None,
):
    # Пояс — устройство (`tz`), иначе Москва; «сегодня» — местное.
    zone = user_tz(tz)
    today = local_today(zone)
    year  = year  or today.year
    month = month or today.month
    return await asyncio.to_thread(_compute_lunar_calendar, year, month, zone)


# ── DEBUG: show house cusps ───────────────────────────────────────────────────
@debug_router.get("/api/v1/chart/{chart_id}/debug/cusps")
async def get_chart_cusps(
    request: Request,
    chart_id: str,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    chart = resolve_chart_access(chart_id, user, chart_token(request), db)
    return {
        "timezone": getattr(chart, "timezone", None),
        "house_system": getattr(chart, "house_system", "unknown"),
        "houses": chart.houses,
    }


# ── Подключение debug-роутов ──
# В проде (DEBUG=false, TESTING=false) роуты не регистрируются вовсе, поэтому
# отсутствуют и в /openapi.json.
if DEBUG_ROUTES_ENABLED:
    app.include_router(debug_router)
else:
    logger.info("Debug routes disabled (DEBUG=false).")
