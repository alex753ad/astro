# Astrea Timeline — Архитектура проекта

> Версия: 3.1 | Июль 2026

---

## 1. Общее описание

**Astrea Timeline** — веб-приложение для построения натальных карт, расчёта транзитов, лунного календаря и генерации AI-интерпретаций.

**Стек:** Python (55.9%) + JavaScript (41.9%) + HTML (1.7%) + CSS (0.3%)

Монетизация — подписочная модель через Stripe: **Free / Lite (790₽) / Pro (1990₽) / Premium (7990₽)**.

---

## 2. Архитектура верхнего уровня

```
┌─────────────────────────────────────────────────────────────┐
│                        ПОЛЬЗОВАТЕЛЬ                          │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTPS
┌──────────────────────────▼──────────────────────────────────┐
│                FRONTEND — Vercel                             │
│  React 18 + React Router 6 + Vite 5 + Tailwind 3.4          │
│  (JavaScript 41.9% + HTML/CSS 2.0%)                         │
│                                                              │
│  pages/          components/        hooks/                   │
│  ├─ LandingPage  ├─ NatalChart.jsx  ├─ useAuth.jsx           │
│  ├─ HomePage     ├─ AuthModal       └─ (fetch + JWT)         │
│  ├─ ChartPage    ├─ Toast                                    │
│  ├─ ProfilePage  └─ ThemeToggle                              │
│  ├─ CRMPage                                                  │
│  ├─ PlannerPage                                              │
│  └─ LunarCalendarPage                                        │
└──────────────────────────┬──────────────────────────────────┘
                           │ REST + SSE
┌──────────────────────────▼──────────────────────────────────┐
│                BACKEND — Railway (FastAPI)                    │
│  Python 3.12 + FastAPI + SQLAlchemy 2.0 + Pydantic 2.7       │
│  (Python 55.9%)                                              │
│                                                              │
│  /api/v1/                                                    │
│  ├─ auth/          JWT + Google OAuth + bcrypt               │
│  ├─ chart/         расчёт натальных карт                     │
│  ├─ clients/       CRM (Premium only)                        │
│  ├─ profile/       карты, история, подписка                  │
│  ├─ payments/      Stripe checkout + webhooks                │
│  ├─ calendar/      лунный календарь                          │
│  ├─ transit/       транзиты + AI-интерпретация SSE           │
│  ├─ interpretation/ RAG-чат                                  │
│  └─ health/        мониторинг                                │
└──────┬───────────────┬────────────────┬─────────────────────┘
       │               │                │
┌──────▼──────┐ ┌──────▼──────┐ ┌──────▼──────────────────────┐
│ PostgreSQL  │ │    Redis     │ │   Внешние сервисы            │
│ Railway     │ │   Railway    │ │                              │
│             │ │             │ │  OpenAI GPT-4o               │
│ users       │ │ interp.     │ │  DeepSeek V3 (fallback)      │
│ natal_charts│ │ cache       │ │  Template engine (fallback)  │
│ interpret.  │ │ transit     │ │  Swiss Ephemeris (local)     │
│ subscript.  │ │ cache       │ │  Stripe (платежи)            │
│ astrologer_ │ │ rate        │ │  Resend (email)              │
│ profiles    │ │ limits      │ │  Google OAuth                │
│ client_     │ │             │ │  Nominatim (геокодинг)       │
│ profiles    │ └─────────────┘ └──────────────────────────────┘
│ gift_codes  │
└─────────────┘
       │
┌──────▼──────────────────────────────────────────────────────┐
│              CELERY WORKER — Railway                         │
│                                                              │
│  tasks/                                                      │
│  ├─ schedule_retention_emails  (день 2, 7, 14)               │
│  ├─ schedule_lite_emails       (день 1, 14)                  │
│  ├─ schedule_pro_emails        (день 1, 30)                  │
│  ├─ schedule_premium_emails    (день 1)                      │
│  ├─ send_weekly_digest_task    (каждый пн, 06:00 UTC)        │
│  ├─ check_lunar_returns        (ежедневно)                   │
│  └─ generate_pdf               (по запросу)                  │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Технологический стек

| Слой | Технология |
|---|---|
| Frontend | React 18.3, React Router 6, Vite 5, Tailwind 3.4 (JavaScript 41.9%) |
| Backend | Python 3.12, FastAPI, Uvicorn (Python 55.9%) |
| ORM / БД | SQLAlchemy 2.0, Alembic, PostgreSQL 16 |
| Кэш / очереди | Redis 7, Celery |
| Астрология | pyswisseph (Swiss Ephemeris), ephemeris-файлы `.se1` |
| AI | OpenAI GPT-4o → DeepSeek V3 → шаблоны |
| Аутентификация | JWT (python-jose), Google OAuth 2.0, bcrypt |
| Платежи | Stripe (checkout sessions, webhooks, portal) |
| Email | Resend API |
| Геокодинг | Nominatim (OpenStreetMap) |
| Rate limiting | slowapi (per-tier) |
| Deploy | Railway (backend + worker + cron), Vercel (frontend) |
| CI/CD | GitHub Actions |
| PDF | ReportLab |
| Markup | HTML/CSS 2.0%, Dockerfile 0.1%, Batchfile 0.1% |

---

## 4. Структура backend

```
backend/
├── main.py                  # FastAPI app, все роутеры
├── models.py                # SQLAlchemy модели
├── schemas.py               # Pydantic схемы
├── config.py                # Settings (pydantic-settings)
├── database.py              # engine, SessionLocal, Base
├── cache.py                 # Redis wrapper
├── tasks.py                 # Celery tasks (email chains, PDF)
├── celery_app.py            # Celery конфигурация
├── email_service.py         # Resend — все шаблоны писем
├── natal_pdf.py             # PDF генератор (ReportLab)
├── health.py                # health checks
├── limiter.py               # rate limiter
├── onboarding_router.py     # onboarding steps API
├── share_router.py          # публичные ссылки на карты
│
├── auth/                    # JWT, Google OAuth, зависимости
├── calendar/                # лунный календарь
├── crm/                     # CRM клиентов (Premium)
│   └── crm_router.py        # CRUD клиентов + карты + транзиты
├── ephemeris/               # Swiss Ephemeris обёртка
│   ├── calculator.py        # расчёт карты
│   ├── geo.py               # геокодинг + UTC
│   └── aspects.py           # аспекты
├── interpretation/          # AI интерпретации
│   ├── router.py            # fallback chain (GPT→DS→template)
│   ├── base.py              # базовые классы
│   └── rag_router.py        # RAG-чат
├── payments/                # Stripe интеграция
├── profile/                 # профиль, история, подписка
└── transit/                 # транзиты
    ├── engine.py            # calculate_transits()
    └── prompts.py           # AI промпты для транзитов
```

---

## 5. Структура frontend

```
frontend/src/
├── App.jsx                  # роутинг, header, auth modal
├── main.jsx                 # entry point
├── index.css                # глобальные стили
│
├── pages/
│   ├── LandingPage.jsx      # главная (неавторизованные)
│   ├── HomePage.jsx         # главная (авторизованные)
│   ├── ChartPage.jsx        # натальная карта + интерпретация
│   ├── ProfilePage.jsx      # ЛК: карты, история, подписка, CRM
│   ├── CRMPage.jsx          # база клиентов (Premium)
│   ├── PlannerPage.jsx      # астро-планировщик
│   ├── LunarCalendarPage.jsx# лунный календарь
│   ├── ZodiacPage.jsx       # характеристика знака
│   ├── SharePage.jsx        # публичная карта по токену
│   └── GiftPage.jsx         # подарочные коды
│
├── components/
│   ├── NatalChart.jsx       # SVG колесо натальной карты
│   ├── AuthModal.jsx        # вход / регистрация
│   ├── Toast.jsx            # уведомления
│   └── ThemeToggle.jsx      # переключатель темы
│
└── hooks/
    └── useAuth.jsx          # auth context + authFetch
```

---

## 6. База данных

| Таблица | Назначение |
|---|---|
| `users` | аккаунты, тариф, Stripe ID, Google sub |
| `natal_charts` | карты (планеты, дома, аспекты, ASC, MC) |
| `interpretations` | кэш AI-интерпретаций |
| `subscriptions` | Stripe подписки |
| `coupons_sent` | отправленные купоны (дедупликация) |
| `astrologer_profiles` | профили астрологов (Premium) |
| `client_profiles` | клиенты CRM (Premium) |
| `gift_codes` | подарочные коды |

**Миграции:** Alembic, 14 версий (`001_initial` → `014_gift_codes`)

---

## 7. API эндпоинты

| Метод | Путь | Описание |
|---|---|---|
| POST | `/api/v1/chart/calculate` | Расчёт натальной карты |
| GET | `/api/v1/chart/{id}` | Получить карту |
| GET | `/api/v1/chart/{id}/interpret` | AI-интерпретация (SSE) |
| GET | `/api/v1/chart/{id}/transits` | Транзиты за период |
| GET | `/api/v1/chart/{id}/transits/interpret` | AI-интерпретация транзитов (SSE) |
| GET | `/api/v1/chart/{id}/forecast/daily` | Дневной прогноз |
| GET | `/api/v1/chart/{id}/forecast/weekly` | Недельный прогноз |
| GET | `/api/v1/chart/{id}/forecast/monthly` | Месячный прогноз |
| POST | `/api/v1/auth/register` | Регистрация |
| POST | `/api/v1/auth/login` | Вход |
| GET | `/api/v1/auth/google` | Google OAuth |
| GET | `/api/v1/profile/charts` | Список карт пользователя |
| GET | `/api/v1/profile/subscription` | Подписка + фичи |
| POST | `/api/v1/payments/checkout` | Создать Stripe checkout |
| POST | `/api/v1/payments/webhook` | Stripe webhook |
| POST | `/api/v1/clients` | Создать клиента CRM |
| GET | `/api/v1/clients` | Список клиентов CRM |
| GET | `/api/v1/clients/{id}/chart` | Карта клиента |
| GET | `/api/v1/clients/{id}/transits` | Транзиты клиента |
| POST | `/api/v1/clients/{id}/report` | PDF отчёт клиента |
| GET | `/health` | Health check |

---

## 8. Email-цепочки

```
Регистрация + первая карта
  └─ Welcome email (сразу)
  └─ Day 2: актуальный транзит
  └─ Day 7: апгрейд-нудж (N транзитов закрыто)
  └─ Day 14: купон 30% на Lite годовой

Апгрейд на Lite
  └─ Welcome Lite (сразу)
  └─ Day 14: тизер RAG-чата → Pro

Апгрейд на Pro
  └─ Welcome Pro (сразу)
  └─ Day 30: результат + намёк на Premium/CRM

Апгрейд на Premium
  └─ Welcome Premium — CRM онбординг (сразу)

Еженедельно (Pro/Premium, пн 06:00 UTC)
  └─ Дайджест: топ-3 транзита + лунные фазы + лучшие дни

Триггеры
  └─ Транзитный алерт (Jupiter/Saturn/Uranus/Neptune)
  └─ Лунное возвращение (Луна в натальном знаке)
  └─ Ошибка оплаты → Stripe Portal
  └─ Подарочный код → покупателю
```

**Транспорт:** Resend API (`RESEND_API_KEY`)

---

## 9. Тарифная сетка

| | Free | Lite | Pro | Premium |
|---|---|---|---|---|
| Цена | 0 | 790₽/мес | 1990₽/мес | 7990₽/мес |
| Карты в месяц | 1/день | 5 | ∞ | ∞ |
| AI-интерпретации | — | 3 | 15 | 100 |
| Транзиты | — | ✓ | ✓ | ✓ |
| PDF-отчёты | — | — | 5 | ∞ |
| RAG-чат | — | — | ✓ | ✓ |
| CRM клиентов | — | — | — | ✓ |
| Брендирование PDF | — | — | — | ✓ |

---

## 10. Деплой

```
GitHub
  └─ push → main
       ├─ GitHub Actions → тесты (pytest)
       ├─ Railway → autodeploy backend
       │    ├─ FastAPI (uvicorn, port 8000)
       │    ├─ Celery worker (redis broker)
       │    └─ Cron: weekly-digest (пн 06:00 UTC)
       └─ Vercel → autodeploy frontend
```

**Переменные окружения (Railway):**
`DATABASE_URL`, `REDIS_URL`, `SECRET_KEY`, `OPENAI_API_KEY`, `RESEND_API_KEY`, `FROM_EMAIL`, `APP_URL`, `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `[...]`

---

## 11. AI Fallback Chain

```
Запрос интерпретации
  └─ GPT-4o (OpenAI)
       └─ [если недоступен/лимит] → DeepSeek V3
            └─ [если недоступен] → Template engine (Python, без AI)
```

Контроль расходов: daily budget per engine + per-tier rate limits через `slowapi`.

---

## 12. Метрики проекта

- **Языки:** Python 55.9% | JavaScript 41.9% | HTML 1.7% | CSS 0.3% | Batchfile 0.1% | Dockerfile 0.1%
- **Среда:** Production (Railway + Vercel)
- **Версия документации:** 3.1 | Июль 2026
