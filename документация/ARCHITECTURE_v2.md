# Astro SPA — Архитектура проекта (v2.0)

Документ описывает текущую архитектуру системы. Источник истины — код в репозитории.

## 1. Назначение

Astro SPA — веб-приложение для построения натальных карт, расчёта транзитов, лунного календаря и генерации персональных астрологических интерпретаций с помощью LLM.

Монетизация — подписочная модель (free / pro / premium) через Stripe.

| Свойство | Реализация |
|---|---|
| Точность расчётов | Swiss Ephemeris (pyswisseph), < 1 угл. сек |
| Стриминг текста | Server-Sent Events |
| Устойчивость к сбоям LLM | GPT-4o -> DeepSeek -> шаблоны |
| Контроль расходов | Daily budget + per-tier rate limits |
| Безопасность | JWT + Google OAuth + bcrypt |
| Планировщик | house_passages (бисекция) + AI |
| Лунный календарь | Фазы, знаки, рекомендации |

## 2. Архитектура верхнего уровня

Frontend (Vercel) -> Backend (Railway, FastAPI) -> PostgreSQL + Redis
Backend -> OpenAI / DeepSeek / Anthropic (LLM)
Backend -> Stripe (платежи)
Backend -> Google OAuth
Backend -> Nominatim (геокодинг)
Backend -> Swiss Ephemeris (файлы .se1)

## 3. Технологический стек

### Backend
- Python 3.12 (Docker: python:3.12-slim)
- FastAPI — асинхронный фреймворк
- SQLAlchemy 2.0 + Alembic — ORM и миграции
- PostgreSQL 16 (psycopg2-binary)
- Redis — кэш
- pyswisseph — Swiss Ephemeris
- pydantic 2.7 + pydantic-settings
- python-jose — JWT
- passlib[bcrypt] — пароли
- slowapi — rate limiting
- httpx — HTTP-клиент к LLM
- pytz + timezonefinder — часовые пояса
- geopy — геокодинг

### Frontend
- React 18.3 + React Router 6.23
- Vite 5 — сборка
- Tailwind 3.4 — стили
- D3.js 7.9 — SVG-колесо зодиака

### Инфраструктура
- Docker Compose (PostgreSQL + Redis + API)
- Railway — backend production
- Vercel — frontend production
- GitHub Actions — CI/CD

## 4. Backend: структура модулей

```
backend/
  main.py                   — FastAPI app, все эндпоинты
  config.py                 — Settings (env, redis_url)
  database.py               — SQLAlchemy engine, get_db
  models.py                 — User, NatalChart, Interpretation, Subscription
  schemas.py                — Pydantic схемы
  cache.py                  — Redis TTL-кэш (fallback: in-memory)

  ephemeris/
    calculator.py           — планеты, дома, ASC, MC
    aspects.py              — аспекты + орбы
    houses.py               — системы домов
    geo.py                  — геокодинг + DST

  interpretation/
    base.py                 — InterpretationEngine ABC
    router.py               — fallback-цепочка + бюджет
    gpt4o.py                — OpenAI
    deepseek.py             — DeepSeek
    template.py             — шаблоны (всегда работает)
    prompts.py              — промпты
    knowledge_base.json     — база шаблонов

  transit/
    engine.py               — окна транзитов (start/peak/end)
    house_passages.py       — переходы планет по домам (бисекция)
    planner_engine.py       — логика планировщика
    forecast_prompt.py      — промпты daily/weekly/monthly/planner
    prompts.py              — базовые транзитные промпты

  calendar/
    lunar_engine.py         — фазы Луны, знак по дням

  auth/
    jwt.py                  — access (15м), refresh (7д)
    passwords.py            — bcrypt
    oauth.py                — Google OAuth
    dependencies.py         — get_current_user, require_tier
    rate_limits.py          — per-tier лимиты
    router.py               — /api/v1/auth/*

  payments/
    stripe_service.py       — Checkout, Portal, webhooks
    router.py               — /api/v1/payments/*
    payments_router.py      — доп. эндпоинты

  profile/
    router.py               — карты, история, GDPR
    settings_router.py      — настройки

  tests/
    conftest.py, test_calculator.py, test_ephemeris.py,
    test_validation.py, test_api.py, test_auth.py,
    test_interpretation.py, test_transits.py,
    test_payments.py, test_profile.py
```

## 5. Frontend: структура

```
frontend/src/
  App.jsx                   — AuthProvider + Routes + Header + AuthModal
  main.jsx                  — ReactDOM root
  index.css                 — Tailwind + тема
  PlannerPage.jsx           — персональный планировщик

  api/client.js             — REST + SSE + getLunarCalendar

  pages/
    HomePage.jsx            — форма ввода
    ChartPage.jsx           — карта / транзиты / планировщик
    ProfilePage.jsx         — профиль
    LunarCalendarPage.jsx   — лунный календарь

  components/
    AuthModal.jsx           — модальное окно авторизации
    BirthForm.jsx           — форма данных рождения
    NatalChart.jsx          — D3 SVG-колесо (preserveAspectRatio)
    ChartSummary.jsx        — сводка
    AspectTable.jsx         — таблица аспектов
    AspectGrid.jsx          — сетка аспектов
    Interpretation.jsx      — SSE-стриминг (auto-reconnect x3)
    TransitTimeline.jsx     — timeline транзитов
    TransitEventDetail.jsx  — детали транзита
    AstroCalendar.jsx       — календарный вид
    ForecastScale.jsx       — шкала прогноза
    ExpertModeToggle.jsx    — экспертный режим

  hooks/useAuth.jsx         — AuthProvider + useAuth
```

### Маршруты

| Путь | Компонент |
|---|---|
| / | HomePage |
| /chart/:chartId | ChartPage |
| /planner/:id | PlannerPage |
| /lunar | LunarCalendarPage |
| /profile | ProfilePage |

## 6. API Endpoints

### Chart
- POST /api/v1/chart/calculate — расчёт натальной карты
- GET /api/v1/chart/{id} — получить карту
- GET/POST /api/v1/chart/{id}/interpret — AI-интерпретация (SSE/full)

### Transits & Forecast
- GET /api/v1/chart/{id}/transits — транзиты за период
- GET /api/v1/chart/{id}/transits/interpret — обзор транзитов (SSE)
- POST /api/v1/chart/{id}/transits/event/interpret — один транзит
- GET /api/v1/chart/{id}/forecast/daily — дневной прогноз
- GET /api/v1/chart/{id}/forecast/weekly — недельный прогноз
- GET /api/v1/chart/{id}/forecast/monthly — месячный прогноз
- GET /api/v1/chart/{id}/planner/monthly — планировщик

### Calendar
- GET /api/v1/calendar/lunar — лунный календарь

### Auth
- POST /api/v1/auth/register, login, refresh, google
- GET /api/v1/auth/me
- DELETE /api/v1/auth/me — GDPR удаление

### Payments
- POST /api/v1/payments/checkout, portal, webhook
- GET /api/v1/payments/subscription

### Health
- GET /health, /health/db, /health/ai

## 7. Ключевые модули

### house_passages.py — переходы планет по домам
- Шаг: Луна 0.5ч, Солнце 6ч, медленные 24ч
- Бисекция (20 итераций) для точного момента
- user_timezone: сканирование в UTC, отображение в локальном
- compute_planner_periods() — структура для AI-промпта

### transit/engine.py — транзиты
- Сканирование 4ч шагом
- Окна: start_date / peak_date / end_date
- Тернарный поиск точного пика (12 итераций)
- get_active_transits(), get_planet_positions_for_date()

### interpretation/router.py — AI fallback
- GPT-4o -> DeepSeek -> шаблоны
- 3 retry, экспоненциальная задержка (1с, 3с, 9с)
- Budget guard (AI_DAILY_BUDGET_USD)
- Кэш 30 дней

### forecast_prompt.py — промпты из методички
- HOUSE_SPHERE_MAP — 12 домов -> сферы
- MOON_HOUSE_ACTIONS — Луна в каждом доме
- PLANET_HOUSE_MEANINGS — все планеты по домам
- Промпты: daily, weekly, monthly, planner

## 8. Деплой

- Frontend: Vite build -> Vercel
- Backend: Dockerfile -> Railway
- PostgreSQL: Railway managed (${{Postgres.DATABASE_URL}})
- Redis: Railway / Docker
- CI/CD: GitHub Actions
- Alembic: автозапуск при старте (railway.toml)

Миграции: 001_initial, 002_subscriptions, 003_users_auth_stripe, 004_expert_mode

## 9. Конфигурация (.env)

DATABASE_URL, REDIS_URL, OPENAI_API_KEY, DEEPSEEK_API_KEY,
ANTHROPIC_API_KEY, AI_DAILY_BUDGET_USD, JWT_SECRET,
STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, STRIPE_PRICE_ID_PRO,
STRIPE_PRICE_ID_PREMIUM, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET,
EPHE_PATH, DEBUG, CORS_ORIGINS

## 10. Безопасность

- Секреты только в .env
- Пароли: bcrypt
- CORS: конкретный домен
- Stripe webhook: проверка подписи
- JWT: access 15м + refresh 7д
- GDPR: полное удаление аккаунта
- Rate limiting: slowapi + per-tier
- SQL injection: SQLAlchemy ORM

---

Версия: 2.0 | Май 2026
