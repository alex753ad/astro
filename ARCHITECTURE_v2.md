# Astrea Timeline — Архитектура проекта (v2.2)

Документ описывает текущую архитектуру системы. Источник истины — код в репозитории.

## 1. Назначение

Astrea Timeline — веб-приложение для построения натальных карт, расчёта транзитов, лунного календаря и генерации персональных астрологических интерпретаций с помощью LLM.

Монетизация — подписочная модель **4 тарифов: Free / Lite (790₽) / Pro (1990₽) / Premium (7990₽)** через Stripe. Trial отсутствует.

| Свойство | Реализация |
|---|---|
| Точность расчётов | Swiss Ephemeris (pyswisseph), < 1 угл. сек |
| Стриминг текста | Server-Sent Events (секционный, с `section_start`/`section_end`) |
| Устойчивость к сбоям LLM | GPT-4o → DeepSeek → шаблоны |
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
OpenAI / DeepSeek (LLM, fallback-цепочка)
    ↓
Stripe (платежи, 6 прайсов + Coupon API)
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
- Redis — кэш (transit_cache, geo_cache, interp_cache)
- pyswisseph — Swiss Ephemeris
- pydantic 2.7 + pydantic-settings
- python-jose — JWT
- passlib[bcrypt] — пароли
- slowapi — rate limiting
- httpx — HTTP-клиент к LLM + Resend
- pytz + timezonefinder — часовые пояса
- geopy — геокодинг
- Celery — фоновые задачи (retention email chain)

### Frontend
- React 18.3 + React Router 6.23
- Vite 5 — сборка
- Tailwind 3.4 — стили
- D3.js 7.9 — SVG-колесо зодиака

### Инфраструктура
- Docker Compose (PostgreSQL + Redis + API)
- Railway — backend production + Celery worker + Railway Cron
- Vercel — frontend production
- GitHub Actions — CI/CD
- Resend — транзакционные письма (домен: astreatime.ru)

## 4. Тарифная сетка

| Параметр | Free | Lite | Pro | Premium |
|---|---|---|---|---|
| Цена | 0 | 790₽/мес | 1990₽/мес | 7990₽/мес |
| Карты в месяц | 1/день | 5 | ∞ | ∞ |
| AI-интерпретации | — | 3 | 15 | 100 |
| Слов в интерпретации | — | 800 | 2500 | 5000 |
| Транзиты (просмотр) | — | ✓ | ✓ | ✓ |
| AI-расшифровка транзитов | — | — | ✓ | ✓ |
| RAG-чат | — | — | ✓ | — |
| PDF-отчёты | — | — | 5/мес | 50/мес |
| CRM клиентов | — | — | — | ✓ |
| Лунный календарь | 1 мес | 12 мес | 12 мес | 12 мес |
| Планировщик | — | 1 мес | 12 мес | 12 мес |

Иерархия тарифов: `free < lite < pro < premium`
`require_tier("pro")` → пропускает pro и premium.

## 5. Backend: структура модулей

```
backend/
  main.py                   — FastAPI app, все эндпоинты
  config.py                 — Settings (env, 6 Stripe price IDs)
  database.py               — SQLAlchemy engine, get_db
  models.py                 — User, NatalChart, Interpretation, Subscription, CouponSent
  schemas.py                — Pydantic схемы
  cache.py                  — Redis TTL-кэш (fallback: in-memory)
  celery_app.py             — Celery instance
  tasks.py                  — Celery tasks: retention emails (day2/7/14), PDF, transits
  email_service.py          — Resend API, 8 шаблонов писем
  onboarding_router.py      — /api/v1/internal/* (Railway Cron)

  ephemeris/
    calculator.py           — планеты, дома, ASC, MC
    aspects.py              — аспекты + орбы + importance (high/medium/low)
    houses.py               — системы домов
    geo.py                  — геокодинг + DST

  interpretation/
    base.py                 — InterpretationEngine ABC
    router.py               — fallback-цепочка + бюджет + circuit breaker
    gpt4o.py                — OpenAI
    deepseek.py             — DeepSeek
    template.py             — шаблоны (всегда работает)
    prompts.py              — промпты с XML-секциями (section_start/end SSE)
    knowledge_base.json     — база шаблонов

  transit/
    engine.py               — окна транзитов (start/peak/end) + transit alerts
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
    dependencies.py         — get_current_user, get_current_user_optional,
                              require_tier (иерархия), TIER_HIERARCHY
    rate_limits.py          — TIER_FLAGS (4 тарифа, rag_chat, crm, pdf),
                              TierRateLimiter, get_tier_limits
    router.py               — /api/v1/auth/*

  payments/
    stripe_service.py       — Checkout (6 прайсов), Portal, webhooks,
                              create_day14_coupon, handle_payment_failed
    router.py               — /api/v1/payments/*

  profile/
    router.py               — карты, история, subscription (Feature Flags), GDPR
    settings_router.py      — настройки

  tests/
    conftest.py             — SQLite, фикстуры, моки
    test_sprint2.py         — tier hierarchy, coupon, subscription endpoint (15 тестов)
    test_payments.py        — Stripe: checkout, portal, webhooks (25 тестов)
    test_stripe.py          — webhook events (12 тестов)
    test_profile.py         — /profile/* endpoints
    test_rate_limits.py     — tier enforcement
    test_auth.py            — register, login, refresh, google
    test_calculator.py, test_ephemeris.py,
    test_validation.py, test_api.py,
    test_interpretation.py, test_transits.py
```

## 6. Frontend: структура

```
frontend/src/
  App.jsx                   — AuthProvider + Routes + Header + AuthModal
  main.jsx                  — ReactDOM root
  index.css                 — CSS variables (light/dark theme)

  api/client.js             — REST + SSE + getLunarCalendar
                              API_BASE: https://astro-production-abcc.up.railway.app/api/v1

  pages/
    HomePage.jsx            — лендинг + форма ввода
    ChartPage.jsx           — 5 вкладок: Карта/Интерпретация/Аспекты/Транзиты/Планировщик🔒
                              tab в URL: /chart/:id?tab=transits
    ProfilePage.jsx         — профиль, тариф (Free/Lite/Pro/Premium), подписка
    LunarCalendarPage.jsx   — лунный календарь

  components/
    AuthModal.jsx           — модальное окно авторизации/регистрации
    BirthForm.jsx           — форма данных рождения
    NatalChart.jsx          — D3 SVG-колесо (preserveAspectRatio)
    ChartSummary.jsx        — сводка планет
    AspectTable.jsx         — таблица аспектов + importance badge (Влиятельный/Обычный/Минорный)
    AspectGrid.jsx          — сетка аспектов
    Interpretation.jsx      — SSE-стриминг, секционный рендер, нарративный обрыв + paywall
    TransitTimeline.jsx     — timeline транзитов + blur для free/lite
    TransitEventDetail.jsx  — детали транзита
    AstroCalendar.jsx       — календарный вид
    ForecastScale.jsx       — шкала прогноза
    OnboardingTooltips.jsx  — 3 тултипа: ASC / MC / Аспекты (flag: astrea_onboarding_seen)
    PaywallModal.jsx        — 3 контекста: free→lite / lite→pro / pro→premium
                              Активируется по 403 { error: "tier_required" }
    StreakBadge.jsx         — счётчик дней подряд
    ThemeToggle.jsx         — dark/light тема (astrea_theme в localStorage)
    ExpertModeToggle.jsx    — экспертный режим

  hooks/useAuth.jsx         — AuthProvider + useAuth + анонимная карта из localStorage
```

### Маршруты

| Путь | Компонент |
|---|---|
| / | HomePage (лендинг) |
| /chart/:chartId | ChartPage (5 вкладок) |
| /planner/:id | PlannerPage |
| /lunar | LunarCalendarPage |
| /profile | ProfilePage |

### Анонимный флоу
1. Расчёт без авторизации → `{ chartData, timestamp, expiresAt }` в `localStorage`
2. CTA "Войдите, чтобы сохранить карту"
3. После OAuth/login → `POST /api/v1/chart/save-anonymous` → привязка к аккаунту

## 7. API Endpoints

### Chart
- `POST /api/v1/chart/calculate` — расчёт (авторизация опциональна; первая карта → Celery retention chain)
- `POST /api/v1/chart/save-anonymous` — сохранить анонимную карту после логина
- `GET /api/v1/chart/{id}` — получить карту
- `GET|POST /api/v1/chart/{id}/interpret` — AI-интерпретация (SSE, секционный стриминг)

### Transits & Forecast
- `GET /api/v1/chart/{id}/transits` — транзиты за период (требует lite+)
- `GET /api/v1/chart/{id}/transits/interpret` — AI-обзор транзитов (SSE, требует pro+)
- `POST /api/v1/chart/{id}/transits/event/interpret` — один транзит
- `GET /api/v1/chart/{id}/transits/async` — фоновый расчёт (Celery)
- `GET /api/v1/chart/{id}/forecast/daily|weekly|monthly` — прогнозы
- `GET /api/v1/chart/{id}/planner/monthly` — планировщик (требует pro+)

### Calendar
- `GET /api/v1/calendar/lunar` — лунный календарь

### Auth
- `POST /api/v1/auth/register, login, refresh, google`
- `GET /api/v1/auth/me`
- `DELETE /api/v1/auth/me` — GDPR удаление аккаунта

### Payments
- `POST /api/v1/payments/checkout` — создать Stripe Checkout (tier + billing_period, без trial)
- `POST /api/v1/payments/portal` — Stripe Customer Portal
- `POST /api/v1/payments/webhook` — Stripe webhook (checkout, sub_updated, sub_deleted, payment_failed)

### Profile
- `GET /api/v1/profile/charts` — список карт
- `DELETE /api/v1/profile/charts/{id}` — удалить карту
- `GET /api/v1/profile/history` — история интерпретаций
- `GET /api/v1/profile/subscription` — **Feature Flags**: tier + limits + usage
- `DELETE /api/v1/profile/data` — GDPR: удалить все данные

### Internal (Railway Cron / X-Internal-Secret)
- `POST /api/v1/internal/onboarding-emails` — Day2 + Day7 письма
- `POST /api/v1/internal/weekly-digest` — еженедельный дайджест (каждый пн 09:00 МСК)
- `POST /api/v1/internal/coupon/generate` — Day14 купон 30% (один на пользователя)

### Health
- `GET /health, /health/db, /health/ai`

## 8. Email система

### Сервис: Resend
- Домен: `astreatime.ru` (SPF + DKIM + DMARC)
- FROM: `noreply@astreatime.ru`

### Шаблоны (`backend/email_service.py`)

| Функция | Триггер | Содержание |
|---|---|---|
| `send_welcome_email` | Первая натальная карта | Солнце в [Знак] + инсайт |
| `send_retention_day2` | Celery, delay 48ч | Ближайший активный транзит |
| `send_retention_day7` | Celery, delay 7д, только free | Loss-aversion: N пропущенных транзитов |
| `send_retention_day14` | Celery, delay 14д, только free | Купон 30% на годовой Lite (24ч, один раз) |
| `send_payment_failed_email` | Webhook invoice.payment_failed | Ссылка на Stripe Portal, grace 3д |
| `send_weekly_digest` | Railway Cron пн 09:00 МСК, pro/premium | 3 дня недели + транзиты + луна |
| `send_transit_alert_email` | Медленная планета начинает проход | Юпитер/Сатурн/Уран/Нептун |

### Celery retention chain
При первой карте авторизованного пользователя → `schedule_retention_emails.delay(user_id)`:
- Day 2: реальный транзит из Transit Engine
- Day 7: список 3 пропущенных транзитов (только free)
- Day 14: Stripe Coupon 30%, один на пользователя (CouponSent таблица)

## 9. Конверсионная воронка (Frontend)

### Онбординг-тултипы (D1)
- Показываются при первом просмотре карты
- 3 шага: ASC → MC → Аспекты
- `astrea_onboarding_seen` в localStorage

### Нарративный обрыв (D2)
- AI-интерпретация обрывается на эмоционально значимой теме
- Выбор темы: 7-й дом → отношения; Луна → эмоции; иначе → Сатурн
- Blur + CTA "Читать полную интерпретацию" → PaywallModal free_to_lite

### PaywallModal (D3)
Контекст определяется по `403 { error: "tier_required", required: "..." }`:

| Контекст | Заголовок | CTA |
|---|---|---|
| `free_to_lite` | "Прочитайте полную интерпретацию" | Lite — 790 ₽/мес |
| `lite_to_pro` | "Разблокируйте ваши транзиты" | Pro — 1 990 ₽/мес |
| `pro_to_premium` | "Работаете с клиентами?" | Premium — 7 990 ₽/мес |

### Транзиты с blur (D4)
- Анонимам и Free: транзитное колесо видно, список с blur
- Кнопка "Открыть Pro" → `lite_to_pro` PaywallModal

## 10. База данных

### Таблицы

| Таблица | Назначение |
|---|---|
| `users` | email, tier (free/lite/pro/premium), stripe_customer_id |
| `natal_charts` | данные карты, planets/houses/aspects JSON, public_token |
| `interpretations` | кэш AI-интерпретаций, profile_hash |
| `subscriptions` | Stripe subscription, tier, status, current_period_end |
| `coupons_sent` | day14 купоны: один на пользователя (unique user_id) |

### Alembic миграции
`001_initial` → `002_subscriptions` → `003_users_auth_stripe` → `004_expert_mode` →
`005_fix_users_not_null` → `006_fix_constraints` → `007_add_lite_tier` →
`008_add_users_name` → `009_coupons_sent` → `010_natal_chart_name_col`

## 11. Деплой

- Frontend: `npm run build` → `vercel --prod`
- Backend: Dockerfile → Railway (автодеплой при push в main)
- Celery: отдельный Railway worker (`celery -A backend.celery_app worker`)
- PostgreSQL: Railway managed
- Redis: Railway / Docker
- CI/CD: GitHub Actions
- Alembic: автозапуск при старте (railway.toml)

## 12. Конфигурация (.env)

```
DATABASE_URL, REDIS_URL
OPENAI_API_KEY, DEEPSEEK_API_KEY, AI_DAILY_BUDGET_USD
JWT_SECRET, JWT_SECRET_PREV
STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET
STRIPE_PRICE_ID_LITE, STRIPE_PRICE_ID_LITE_ANNUAL
STRIPE_PRICE_ID_PRO, STRIPE_PRICE_ID_PRO_ANNUAL
STRIPE_PRICE_ID_PREMIUM, STRIPE_PRICE_ID_PREMIUM_ANNUAL
GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
RESEND_API_KEY, FROM_EMAIL, APP_URL, FRONTEND_URL
EPHE_PATH, DEBUG, ENVIRONMENT
CORS_ORIGINS, INTERNAL_SECRET
```

## 13. Безопасность

- Секреты только в .env
- Пароли: bcrypt
- CORS: список доменов через CORS_ORIGINS
- Stripe webhook: проверка подписи
- JWT: access 15м + refresh 7д + ротация через JWT_SECRET_PREV
- GDPR: полное удаление аккаунта (CASCADE)
- Rate limiting: slowapi + per-tier
- Anti-fraud Premium: SlowAPI 3 req/min + IP-мониторинг Redis (3+ IP за 30 мин → сброс сессии)
- Circuit breaker: AI_DAILY_BUDGET_USD → fallback на template.py
- SQL injection: SQLAlchemy ORM
- Internal endpoints: X-Internal-Secret header

## 14. Тесты

Все тесты используют SQLite in-memory, моки Stripe/OpenAI.

```
backend/tests/
  conftest.py              — SQLite engine, TestClient, fixtures (user_free, user_pro, auth headers)
  test_sprint2.py          — tier hierarchy, rag_chat flags, coupon dedup, /profile/subscription
  test_payments.py         — checkout (6 тарифов), portal, webhooks, TIER_PRICE_MAP
  test_stripe.py           — payment_failed, sub_updated, sub_deleted
  test_profile.py          — charts CRUD, history, subscription Feature Flags
  test_rate_limits.py      — require_tier enforcement (free/lite/pro/premium)
  test_auth.py             — register, login, refresh, google OAuth
  test_calculator.py       — ephemeris calculation
  test_ephemeris.py        — planets, aspects, houses
  test_interpretation.py   — AI cascade, template fallback
  test_transits.py         — transit engine
  test_validation.py       — input validation
  test_api.py              — smoke tests
```

Запуск: `DATABASE_URL="sqlite:///./test.db" TESTING=true pytest backend/tests/ -q`

---

Версия: 2.2 | Май 2026 | Sprint v3.1
