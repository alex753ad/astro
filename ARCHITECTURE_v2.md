# Astrea Timeline — Архитектура проекта (v2.1)

Документ описывает текущую архитектуру системы. Источник истины — код в репозитории.

## 1. Назначение

Astrea Timeline — веб-приложение для построения натальных карт, расчёта транзитов, лунного календаря и генерации персональных астрологических интерпретаций с помощью LLM.

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
| Email | Resend API + SPF/DKIM/DMARC |

## 2. Архитектура верхнего уровня

```
Frontend (Vercel)
    ↓
Backend (Railway, FastAPI)
    ↓
PostgreSQL + Redis
    ↓
OpenAI / DeepSeek / Anthropic (LLM)
    ↓
Stripe (платежи)
    ↓
Resend (транзакционные письма)
    ↓
Google OAuth
    ↓
Nominatim (геокодинг)
    ↓
Swiss Ephemeris (.se1 файлы)
```

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
- httpx — HTTP-клиент к LLM + Resend
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
- Resend — транзакционные письма (домен: astreatime.ru)

## 4. Backend: структура модулей

```
backend/
  main.py                   — FastAPI app, все эндпоинты
  config.py                 — Settings (env, redis_url)
  database.py               — SQLAlchemy engine, get_db
  models.py                 — User, NatalChart, Interpretation, Subscription
  schemas.py                — Pydantic схемы
  cache.py                  — Redis TTL-кэш (fallback: in-memory)
  email_service.py          — Resend API, 6 шаблонов писем
  onboarding_router.py      — /api/v1/internal/onboarding-emails (Railway Cron)

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
- POST /api/v1/chart/calculate — расчёт карты (привязка к user_id если авторизован)
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

### Internal (Railway Cron)
- POST /api/v1/internal/onboarding-emails — Day2 + Day7 письма

### Health
- GET /health, /health/db, /health/ai

## 7. Email система

### Сервис: Resend
- Домен: `astreatime.ru` (SPF + DKIM + DMARC)
- FROM: `noreply@astreatime.ru`
- Конфиг: `RESEND_API_KEY`, `FROM_EMAIL`, `APP_URL`

### Шаблоны (`backend/email_service.py`)

| Функция | Триггер | Содержание |
|---|---|---|
| `send_welcome_email` | Первая натальная карта | Тема: "☀ Ваша карта готова — Солнце в [Знак]" + инсайт по знаку |
| `send_retention_day2` | День 2, Railway Cron | Активный транзит по карте пользователя |
| `send_retention_day7` | День 7, free-юзер | Апгрейд-нудж: N закрытых транзитов |
| `send_trial_ending_email` | За 1–2 дня до конца триала | Напоминание продлить подписку |
| `send_weekly_digest_email` | Еженедельно | Топ-3 транзита на неделю |
| `send_transit_alert_email` | Важный транзит / пик | Точечное уведомление |

### Welcome-логика
1. Пользователь регистрируется → письмо **не** отправляется
2. Пользователь рассчитывает **первую карту** → `calculate_chart` отправляет welcome с инсайтом по знаку Солнца
3. Тема письма персонализирована: `"☀ Ваша натальная карта готова — Солнце в Овне"`

## 8. Деплой

- Frontend: `npm run build` → `vercel --prod`
- Backend: Dockerfile → Railway (автодеплой при push в main)
- PostgreSQL: Railway managed
- Redis: Railway / Docker
- CI/CD: GitHub Actions
- Alembic: автозапуск при старте (railway.toml)

Миграции: 001_initial, 002_subscriptions, 003_users_auth_stripe, 004_expert_mode, 005_fix_users_not_null

## 9. Конфигурация (.env)

```
DATABASE_URL, REDIS_URL
OPENAI_API_KEY, DEEPSEEK_API_KEY, ANTHROPIC_API_KEY, AI_DAILY_BUDGET_USD
JWT_SECRET, JWT_SECRET_PREV
STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, STRIPE_PRICE_ID_PRO, STRIPE_PRICE_ID_PREMIUM
GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
RESEND_API_KEY, FROM_EMAIL, APP_URL, FRONTEND_URL
EPHE_PATH, DEBUG, ENVIRONMENT
ALLOWED_ORIGINS, HTTPS_ONLY
INTERNAL_SECRET
SENTRY_DSN
```

## 10. Безопасность

- Секреты только в .env
- Пароли: bcrypt
- CORS: список доменов через ALLOWED_ORIGINS
- Stripe webhook: проверка подписи
- JWT: access 15м + refresh 7д + ротация через JWT_SECRET_PREV
- GDPR: полное удаление аккаунта (CASCADE)
- Rate limiting: slowapi + per-tier
- SQL injection: SQLAlchemy ORM
- Internal endpoints: X-Internal-Secret header

---

Версия: 2.1 | Май 2026
