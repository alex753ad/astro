# Astrea Timeline — Архитектура проекта (v3.0)

Документ описывает текущую архитектуру системы после масштабной миграции (август 2026).
Источник истины — код в репозитории.

## 1. Назначение и эволюция

**Astrea Timeline** — веб-приложение для построения натальных карт, расчёта транзитов, лунного календаря и генерации персональных прогнозов с использованием AI.

**Версия 3.0** — крупная миграция от простой модели (v2.0) к комплексной платформе:
- ✅ Внутренний планировщик вместо Railway cron (основной процесс app)
- ✅ Celery для асинхронных задач (периодические + тяжёлые вычисления)
- ✅ 20+ новых роутеров для CRM, админ-панели, пилот-программ, обратной связи
- ✅ Новые модели данных: Interpretation, AstrologerProfile и др.
- ✅ Метрики и Sentry для мониторинга
- ✅ RAG, Feedback, Exit Survey системы
- ✅ Онбординг и распределённые уведомления (push)

| Свойство | Реализация |
|---|---|
| Точность расчётов | Swiss Ephemeris (pyswisseph), < 1 угл. сек |
| Стриминг текста | Server-Sent Events (SSE) |
| Устойчивость к сбоям LLM | Claude Sonnet 4 → GPT-4o → DeepSeek V3 → шаблоны |
| Контроль расходов | Daily budget + per-tier rate limits |
| Безопасность | JWT + Google OAuth + bcrypt |
| Планировщик | house_passages (бисекция) + AI |
| Лунный календарь | Фазы, знаки, рекомендации |
| Мониторинг | Prometheus metrics, Sentry, логирование |

## 2. Архитектура верхнего уровня

```
┌─────────────────────────────────────────────────────────────┐
│                     FRONTEND (Vercel)                        │
│                       React 18.3                             │
└────────────────────────┬────────────────────────────────────┘
                         │ HTTPS
┌────────────────────────▼────────────────────────────────────┐
│                  FASTAPI BACKEND (Railway)                   │
│  main.py: lifespan + _scheduler_loop (замена Railway cron)  │
├─────────────────────────────────────────────────────────────┤
│ Роутеры (25+):                                              │
│  • auth, profile, settings, onboarding                       │
│  • chart (calculate, interpret, transits, forecast)         │
│  • payments, admin, crm, pilot, feedback, exit_survey       │
│  • push notifications, advanced_charts, share, rag          │
├─────────────────────────────────────────────────────────────┤
│ Сервисы:                                                     │
│  • interpret: AI fallback (Claude → GPT-4o → DeepSeek)     │
│  • cache: Redis (interpretation, transits, profile hash)    │
│  • metrics: Prometheus, Sentry, EventName tracking         │
└────────────────────────┬────────────────────────────────────┘
                         │
         ┌───────────────┼───────────────┐
         │               │               │
    PostgreSQL         Redis          Celery
      16 (DB)    (Cache, Broker)   (async tasks)
                                        │
                         ┌──────────────┼──────────────┐
                         │              │              │
                    Celery Beat    Worker 1       Worker 2
                   (cron tasks)   (transits)    (mail, alerts)
```

## 3. Технологический стек

### Backend
- **Python 3.12** (Docker: python:3.12-slim)
- **FastAPI** — асинхронный фреймворк
- **SQLAlchemy 2.0 + Alembic** — ORM и миграции БД
- **PostgreSQL 16** (psycopg2-binary)
- **Redis** — кэш и Celery broker/backend
- **Celery** — асинхронные задачи + периодические задачи (Beat)
- **pyswisseph** — Swiss Ephemeris для астрономических расчётов
- **pydantic 2.7** — валидация данных
- **python-jose + passlib[bcrypt]** — JWT и пароли
- **slowapi** — rate limiting
- **httpx** — HTTP-клиент к LLM APIs
- **Anthropic API (Claude Sonnet 4)** — основной AI
- **OpenAI API (GPT-4o)** — fallback AI
- **DeepSeek API (V3)** — второй fallback
- **Prometheus client** — метрики
- **Sentry SDK** — error tracking
- **pytz + timezonefinder** — часовые пояса
- **geopy/Nominatim** — геокодинг

### Frontend
- **React 18.3** + React Router 6.23
- **Vite 5** — сборка
- **Tailwind CSS 3.4** — стили
- **D3.js 7.9** — SVG-колесо зодиака

### Инфраструктура
- **Docker Compose** (PostgreSQL + Redis + API)
- **Railway** — backend production
- **Vercel** — frontend production
- **GitHub Actions** — CI/CD

## 4. Backend: структура модулей

```
backend/
  main.py                   — FastAPI app, lifespan, _scheduler_loop, все endpoints
  config.py                 — Settings (env vars, redis_url, sentry_dsn)
  database.py               — SQLAlchemy engine, SessionLocal, get_db
  celery_app.py             — Celery instance, Beat schedule
  
  models.py                 — User, NatalChart, Interpretation, Subscription, 
                              AstrologerProfile, Feedback, ExitSurvey, etc.
  schemas.py                — Pydantic request/response schemas
  cache.py                  — Redis TTL-кэш (fallback: in-memory)
  limiter.py                — slowapi Limiter instance
  metrics.py                — log_event, EventName, maybe_mark_second_visit
  health.py                 — check_all_services (для /health/ai)
  authz.py                  — assert_chart_access

  ephemeris/
    calculator.py           — calculate_full_chart, планеты, дома, ASC, MC
    aspects.py              — аспекты + орбы
    houses.py               — системы домов
    geo.py                  — geocode_place, resolve_utc_datetime, validate_coordinates

  interpretation/
    base.py                 — InterpretationRequest, InterpretationResult, 
                              InterpretationEngine (ABC)
    router.py               — get_router(), fallback-цепочка (Claude → GPT-4o → DeepSeek)
    anthropic.py            — Claude Sonnet 4 engine (основной)
    openai.py               — GPT-4o engine (fallback)
    deepseek.py             — DeepSeek V3 engine (fallback)
    template.py             — шаблонный engine (всегда работает)
    rag_router.py           — RAG endpoints для загрузки knowledge base
    prompts.py              — промпты

  transit/
    engine.py               — calculate_transits, mark_transit_significance, 
                              is_significant_pair, check_and_send_transit_alerts,
                              compute_exact_facts, get_active_transits
    planner_engine.py       — build_planner, логика планировщика
    forecast_prompt.py      — build_daily/weekly/monthly_forecast_prompt, 
                              build_general_calendar_prompt, parse_forecast_response
    prompts.py              — build_transit_period_prompt, 
                              build_transit_event_prompt

  calendar/
    lunar_engine.py         — get_monthly_calendar, get_moon_phases, 
                              ZODIAC_SIGNS, фазы Луны по дням

  auth/
    jwt.py                  — create_access_token, decode_token
    passwords.py            — bcrypt hash/verify
    oauth.py                — Google OAuth logic
    dependencies.py         — get_current_user, get_current_user_optional, 
                              require_tier
    rate_limits.py          — tier_limiter, get_tier_limits
    router.py               — POST /api/v1/auth/register, login, refresh, google; 
                              GET /me; DELETE /me (GDPR)

  payments/
    stripe_service.py       — Stripe API интеграция
    payments_router.py      — Checkout, Portal, webhooks
    router.py               — платежи endpoints

  profile/
    router.py               — карты, история пользователя
    settings_router.py      — настройки профиля

  push/
    router.py               — регистрация push-токенов
    cron.py                 — run_push_tick (отправка уведомлений)

  crm/
    router.py               — основной CRM функционал
    author_router.py        — астрологи, профили
    portal_router.py        — клиентский портал
    dashboard_router.py     — дашбоард
    note_templates_router.py — шаблоны заметок
    access_router.py        — управление доступом

  admin/
    admin_router.py         — управление пользователями
    promo_router.py         — промо-коды
    stats_router.py         — статистика

  onboarding_router.py      — онбординг новых пользователей
  share_router.py           — поделиться картой
  advanced_charts_router.py — продвинутые типы карт
  feedback.py/router.py     — обратная связь, опросы
  exit_survey/router.py     — exit survey при отписке
  pilot/router.py           — пилот-программы
  pilot/cron.py             — периодические задачи пилот-программ

  email_service.py          — send_welcome_email, schedule_retention_emails
  tasks.py                  — Celery задачи (check_lunar_returns, send_weekly_digest, 
                              task_calculate_transits, etc.)
  natal_pdf.py              — generate_pdf_bytes

  tests/
    conftest.py             — pytest fixtures
    test_*.py               — unit и интеграционные тесты
```

## 5. Frontend: структура

```
frontend/src/
  App.jsx                   — AuthProvider + Routes + Header + AuthModal
  main.jsx                  — ReactDOM root
  index.css                 — Tailwind + тема

  api/client.js             — REST + SSE + getLunarCalendar

  pages/
    HomePage.jsx            — форма ввода данных
    ChartPage.jsx           — карта / транзиты / планировщик
    ProfilePage.jsx         — профиль пользователя
    LunarCalendarPage.jsx   — лунный календарь

  components/
    AuthModal.jsx           — модальное окно авторизации
    BirthForm.jsx           — форма данных рождения
    NatalChart.jsx          — D3 SVE-колесо
    ChartSummary.jsx        — сводка
    AspectTable.jsx         — таблица аспектов
    Interpretation.jsx      — SSE-стриминг интерпретаций
    TransitTimeline.jsx     — timeline транзитов
    ForecastScale.jsx       — шкала прогноза

  hooks/useAuth.jsx         — AuthProvider, useAuth
```

## 6. Основные API Endpoints

### Chart
- `POST /api/v1/chart/calculate` — расчёт натальной карты
- `GET /api/v1/chart/{id}` — получить карту
- `GET /api/v1/chart/{id}/interpret` — SSE интерпретация
- `POST /api/v1/chart/{id}/interpret` — полная интерпретация (JSON)
- `POST /api/v1/chart/save-anonymous` — сохранить анонимную карту
- `POST /api/v1/chart/{id}/pdf` — генерация PDF (Celery)

### Transits
- `GET /api/v1/chart/{id}/transits` — расчёт транзитов за период
- `GET /api/v1/chart/{id}/transits/positions` — позиции планет на дату
- `GET /api/v1/chart/{id}/transits/interpret` — SSE обзор транзитов
- `POST /api/v1/chart/{id}/transits/event/interpret` — один транзит (SSE)
- `POST /api/v1/chart/{id}/transits/async` — async расчёт (Celery)

### Forecasts
- `GET /api/v1/chart/{id}/forecast/daily` — дневной прогноз
- `GET /api/v1/chart/{id}/forecast/weekly` — недельный прогноз
- `GET /api/v1/chart/{id}/forecast/monthly` — месячный прогноз
- `GET /api/v1/chart/{id}/planner/monthly` — планировщик (без AI)

### Calendar
- `GET /api/v1/calendar/lunar` — лунный календарь
- `GET /api/v1/calendar/monthly` — общий астро-календарь

### Auth
- `POST /api/v1/auth/register` — регистрация
- `POST /api/v1/auth/login` — вход
- `POST /api/v1/auth/refresh` — обновление токена
- `POST /api/v1/auth/google` — Google OAuth
- `GET /api/v1/auth/me` — текущий пользователь
- `DELETE /api/v1/auth/me` — GDPR удаление

### Payments
- `POST /api/v1/payments/checkout` — Stripe checkout
- `POST /api/v1/payments/portal` — billing portal
- `POST /api/v1/payments/webhook` — Stripe webhook
- `GET /api/v1/payments/subscription` — статус подписки

### Health & Monitoring
- `GET /health` — базовое здоровье
- `GET /health/db` — здоровье БД
- `GET /health/ai` — здоровье AI провайдеров
- `GET /metrics` — Prometheus метрики

### CRM, Admin, Pilot
- `GET/POST /api/v1/crm/*` — управление клиентами
- `GET/POST /api/v1/admin/*` — администрирование
- `GET/POST /api/v1/pilot/*` — пилот-программы
- `POST /api/v1/feedback` — сбор feedback
- `POST /api/v1/exit-survey` — exit survey

## 7. Миграция данных и изменения

### До (v2.0)
- Railway cron контейнеры для фоновых задач
- Нет асинхронной очереди работ
- Интерпретации не кэшировались в БД
- Минимальная аналитика

### После (v3.0)
- **Встроенный планировщик** — `_scheduler_loop()` запускается при старте app
  - Run push notifications every 15 minutes
  - Send weekly digest every Monday at 06:00 UTC
  - Service role: `SERVICE_ROLE=bot` disables scheduler (worker-only instance)

- **Celery + Beat** для тяжёлых и периодических задач
  - `check-lunar-returns-daily` — проверка лунных возвращений
  - `send-weekly-digest-daily` — еженедельная рассылка
  - `send-client-broadcast-monthly` — ежемесячная рассылка
  - Async transit calculations (> 3 months)

- **Interpretation Model** — сохранение интерпретаций в БД
  - `profile_hash` — дедупликация по натальному профилю
  - 30-дневный кэш

- **AstrologerProfile** — премиум астрологи могут брендировать PDF

- **Новые таблицы**: Feedback, ExitSurvey, Pilot*, Push*, Promotion, etc.

## 8. Рекомендованные переменные окружения

```bash
# Основное
DATABASE_URL="postgresql://user:pass@host/db"
REDIS_URL="redis://host:6379/0"
DEBUG=false
TESTING=false

# JWT и безопасность
JWT_SECRET="<генерируйте: python -c 'import secrets; print(secrets.token_urlsafe(48))'>"
CORS_ORIGINS="https://app.example.com,https://app2.example.com"
TRUSTED_PROXY_IPS="127.0.0.1,10.0.0.0/8"

# LLM API ключи
ANTHROPIC_API_KEY="sk-ant-..."
OPENAI_API_KEY="sk-..."
DEEPSEEK_API_KEY="sk-..."
AI_DAILY_BUDGET_USD=100

# Stripe
STRIPE_SECRET_KEY="sk_live_..."
STRIPE_WEBHOOK_SECRET="whsec_..."
STRIPE_PRICE_ID_PRO="price_..."
STRIPE_PRICE_ID_PREMIUM="price_..."

# Google OAuth
GOOGLE_CLIENT_ID="...apps.googleusercontent.com"
GOOGLE_CLIENT_SECRET="..."

# Ephemeris
EPHE_PATH="data/ephe"

# Мониторинг
SENTRY_DSN="https://...@sentry.io/project_id"

# Планировщик
PUSH_SCHEDULER="on"  # "off" если SERVICE_ROLE=bot
SERVICE_ROLE="api"   # или "bot" для worker
```

## 9. Развёртывание

### Local (Docker Compose)
```bash
docker-compose up
```

### Production (Railway)
- Backend: `python -m backend.main` (FastAPI + scheduler + Celery would need separate worker)
- Worker: `celery -A backend.celery_app worker -l info`
- Beat: `celery -A backend.celery_app beat -l info`

**Railway конфигурация:**
```toml
[build]
builder = "dockerfile"

[start]
cmd = "python -m backend.main"

[crons."daily-cleanup"]
cmd = "python -m backend.tasks cleanup"
schedule = "0 2 * * *"
```

## 10. Безопасность

- Секреты только в `.env` / Railway variables
- Пароли: bcrypt (passlib)
- CORS: конкретные домены (не `*`)
- Stripe webhook: проверка подписи
- JWT: access 15м + refresh 7д
- Google OAuth: OIDC verif
- GDPR: полное удаление аккаунта (`DELETE /auth/me`)
- Rate limiting: slowapi + per-tier (free/pro/premium)
- SQL injection: SQLAlchemy ORM + Pydantic
- Sentry integration для критических ошибок
- Логирование всех валидационных ошибок (422) с санитизацией

## 11. Мониторинг и аналитика

- **Prometheus** — `/metrics` экспортирует метрики
- **Sentry** — при `SENTRY_DSN=...` инициализируется, sample_rate=0.1
- **EventName** tracking — TIMELINE_OPEN, INTERPRETATION_REQUESTED, etc.
- **Метрики в Redis** — для быстрого доступа
- **Логирование** — уровень INFO, логи валидационных ошибок с деталями

## 12. Кэширование

### Redis TTL Cache
- **Interpretation** — 30 дней
- **Transit** — 7 дней
- **Transit Interpretation** — 30 дней (по chart_id, planet, aspect, дата)
- **Profile Hash** — дедупликация интерпретаций

### In-Memory Fallback
Если Redis недоступен, используется in-memory cache (на время сессии).

## 13. AI Fallback Chain

```
User requests interpretation
          ↓
        Check cache (Redis/Memory)
          ↓ (miss)
   Try Claude Sonnet 4 (Anthropic)
          ↓ (fail/budget)
   Try GPT-4o (OpenAI)
          ↓ (fail/budget)
   Try DeepSeek V3 (DeepSeek)
          ↓ (fail/budget)
   Use Template Engine
          ↓
   Return response
```

Бюджет: `AI_DAILY_BUDGET_USD` — глобальный лимит в день.

## 14. Новые возможности в v3.0

✅ **Встроенный планировщик** — безопасная замена Railway cron  
✅ **Celery для async** — масштабируемые фоновые задачи  
✅ **RAG система** — загрузка и поиск по knowledge base  
✅ **Feedback & Exit Survey** — сбор данных о пользователях  
✅ **CRM + Астрологи** — управление клиентами и партнёрами  
✅ **Admin панель** — управление системой  
✅ **Пилот-программы** — тестирование новых функций  
✅ **Push уведомления** — по расписанию  
✅ **Prometheus + Sentry** — полный мониторинг  
✅ **PDF брендирование** — для премиум астрологов  
✅ **Улучшенная интеграция с AI** — Claude Sonnet 4 основной, fallback цепочка  

## Версионирование

| Версия | Дата | Ключевые изменения |
|--------|------|-------------------|
| 1.0 | 2025 | MVP: natal chart, transits |
| 2.0 | май 2026 | AI интерпретации, forecasts, планер |
| 3.0 | август 2026 | Celery, встроенный scheduler, CRM, RAG, мониторинг |

---

**Версия документа:** 3.0  
**Последнее обновление:** август 2026  
**Ответственный:** архитектура системы — alex753ad/astro

