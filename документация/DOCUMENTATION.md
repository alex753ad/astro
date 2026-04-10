# Astro SPA — Полная документация проекта

## Оглавление

1. Структура проекта (все фазы)
2. Карта файлов: какой файл к какой фазе относится
3. Инструкция по установке и первому запуску
4. Порядок запуска в разработке
5. Миграции базы данных (Alembic)
6. Настройка внешних сервисов
7. API-эндпоинты — полный список
8. Тестирование
9. Деплой в production

---

## 1. Структура проекта

```
astro-spa/
├── backend/
│   ├── __init__.py
│   ├── main.py                        # FastAPI app, все роутеры, chart/interpret эндпоинты
│   ├── config.py                      # Pydantic Settings — все env-переменные
│   ├── database.py                    # SQLAlchemy engine, SessionLocal, Base, get_db
│   ├── models.py                      # ORM-модели: User, NatalChart, Interpretation, Subscription
│   ├── schemas.py                     # Pydantic-схемы запросов и ответов (все фазы)
│   ├── cache.py                       # In-memory TTL-кэш
│   │
│   ├── ephemeris/                     # Фаза 1: расчётное ядро
│   │   ├── __init__.py
│   │   ├── calculator.py              # pyswisseph — расчёт позиций планет, домов
│   │   ├── aspects.py                 # Расчёт аспектов + орбы
│   │   ├── houses.py                  # Системы домов (Плацидус, Кох)
│   │   └── geo.py                     # Геокодирование, часовые пояса, валидация координат
│   │
│   ├── interpretation/                # Фаза 2: AI-интерпретация
│   │   ├── __init__.py
│   │   ├── base.py                    # InterpretationEngine ABC, InterpretationRequest/Result
│   │   ├── router.py                  # Маршрутизатор fallback-цепочки
│   │   ├── gpt4o.py                   # GPT-4o реализация
│   │   ├── deepseek.py                # DeepSeek V3 fallback
│   │   ├── template.py                # Шаблонный движок (без LLM)
│   │   └── knowledge_base.json        # База ключевых интерпретаций (300–500 записей)
│   │
│   ├── transit/                       # Фаза 3: транзиты
│   │   ├── __init__.py
│   │   └── engine.py                  # Расчёт транзитов за период
│   │
│   ├── auth/                          # Фаза 4.1: аутентификация
│   │   ├── __init__.py
│   │   ├── jwt.py                     # Создание/верификация JWT (access, refresh, email confirm)
│   │   ├── passwords.py               # Хеширование bcrypt через passlib
│   │   ├── oauth.py                   # Google OAuth 2.0 — обмен code → userinfo
│   │   ├── dependencies.py            # FastAPI Depends: get_current_user, require_tier
│   │   ├── rate_limits.py             # Per-tier rate limiter (charts/day, interp/day)
│   │   └── router.py                  # Эндпоинты: register, login, refresh, google, confirm, me
│   │
│   ├── payments/                      # Фаза 4.2: Stripe
│   │   ├── __init__.py
│   │   ├── stripe_service.py          # Stripe Customer, Checkout, Portal, webhook обработка
│   │   └── router.py                  # Эндпоинты: checkout, portal, webhook, subscription
│   │
│   ├── profile/                       # Фаза 4.3: профиль пользователя
│   │   ├── __init__.py
│   │   └── router.py                  # Эндпоинты: charts list, label, delete, history, settings
│   │
│   └── tests/
│       ├── __init__.py
│       ├── test_ephemeris.py           # Тесты точности расчётов (эталонные карты)
│       ├── test_auth.py                # Тесты регистрации, логина, JWT
│       ├── test_payments.py            # Тесты Stripe webhook обработки
│       └── conftest.py                 # Фикстуры: test DB, test client
│
├── frontend/                          # Фаза 2–3: React SPA
│   ├── src/
│   │   ├── components/
│   │   │   ├── NatalChart.jsx         # D3.js SVG-колесо зодиака
│   │   │   ├── TransitTimeline.jsx    # Горизонтальная шкала транзитов
│   │   │   ├── Interpretation.jsx     # Стриминг AI-текста (SSE)
│   │   │   └── BirthForm.jsx          # Форма ввода данных рождения
│   │   ├── api/
│   │   │   └── client.js              # API-клиент + SSE-подключение
│   │   ├── pages/
│   │   │   ├── Home.jsx
│   │   │   ├── Chart.jsx
│   │   │   ├── Login.jsx              # Фаза 4.1
│   │   │   ├── Register.jsx           # Фаза 4.1
│   │   │   ├── Profile.jsx            # Фаза 4.3
│   │   │   └── Pricing.jsx            # Фаза 4.2
│   │   ├── hooks/
│   │   │   └── useAuth.js             # Хук авторизации (JWT storage, refresh)
│   │   └── App.jsx
│   ├── index.html
│   ├── vite.config.js
│   ├── tailwind.config.js
│   └── package.json
│
├── alembic/                           # Миграции БД
│   ├── env.py                         # Подключение к БД через backend.config
│   ├── script.py.mako                 # Шаблон генерации миграций
│   └── versions/
│       ├── 001_baseline.py            # Базовые таблицы: users, natal_charts, interpretations
│       └── 002_phase4_auth_payments.py # Auth-поля + subscriptions
│
├── data/
│   └── ephe/                          # Эфемеридные файлы Swiss Ephemeris (.se1, ~80 МБ)
│
├── alembic.ini                        # Конфигурация Alembic
├── docker-compose.yml                 # PostgreSQL + API (dev)
├── Dockerfile                         # Multi-stage build (production)
├── Makefile                           # Команды dev, test, migrate, lint
├── pyproject.toml                     # Python-зависимости
├── .env                               # Секреты (НЕ в git)
├── .env.example                       # Шаблон переменных окружения
└── .github/
    └── workflows/
        └── ci.yml                     # GitHub Actions: lint, test, deploy
```


## 2. Карта файлов по фазам

### Фаза 1 — Ядро: эфемериды + API (Дни 1–10)

| Файл | Назначение |
|------|------------|
| `backend/__init__.py` | Инициализация пакета |
| `backend/main.py` | FastAPI app + chart эндпоинты |
| `backend/config.py` | Pydantic Settings |
| `backend/database.py` | SQLAlchemy engine, Session, Base |
| `backend/models.py` | ORM: User, NatalChart |
| `backend/schemas.py` | BirthDataInput, NatalChartResponse и т.д. |
| `backend/ephemeris/calculator.py` | pyswisseph — расчёт планет, домов, ASC, MC |
| `backend/ephemeris/aspects.py` | Расчёт аспектов (0°, 60°, 90°, 120°, 180°) |
| `backend/ephemeris/houses.py` | Плацидус / Кох |
| `backend/ephemeris/geo.py` | Nominatim геокодирование, timezonefinder, DST |
| `docker-compose.yml` | PostgreSQL 16 + API |
| `pyproject.toml` | Зависимости |
| `Makefile` | dev, test, migrate, lint |
| `alembic.ini` + `alembic/` | Миграции |
| `data/ephe/*.se1` | Файлы эфемерид |

### Фаза 2 — AI-интерпретация + Frontend (Дни 11–24)

| Файл | Назначение |
|------|------------|
| `backend/interpretation/base.py` | InterpretationEngine ABC |
| `backend/interpretation/router.py` | Fallback-маршрутизатор: GPT-4o → DeepSeek → шаблоны |
| `backend/interpretation/gpt4o.py` | GPT-4o через httpx + SSE |
| `backend/interpretation/deepseek.py` | DeepSeek V3 fallback |
| `backend/interpretation/template.py` | Шаблонный движок |
| `backend/interpretation/knowledge_base.json` | 300–500 записей интерпретаций |
| `backend/cache.py` | In-memory TTL-кэш |
| `frontend/src/components/BirthForm.jsx` | Форма ввода |
| `frontend/src/components/NatalChart.jsx` | D3.js SVG-колесо |
| `frontend/src/components/Interpretation.jsx` | SSE-стриминг текста |
| `frontend/src/api/client.js` | API-клиент |

### Фаза 3 — Транзиты + UX (Дни 25–35)

| Файл | Назначение |
|------|------------|
| `backend/transit/engine.py` | Расчёт транзитов за период |
| `frontend/src/components/TransitTimeline.jsx` | Timeline-компонент |

### Фаза 4.1 — Аутентификация (Дни 36–39)

| Файл | Назначение |
|------|------------|
| `backend/auth/__init__.py` | Пакет |
| `backend/auth/jwt.py` | JWT: access (15 мин), refresh (7 дней), email confirm (24 ч) |
| `backend/auth/passwords.py` | bcrypt хеширование |
| `backend/auth/oauth.py` | Google OAuth 2.0 |
| `backend/auth/dependencies.py` | `get_current_user`, `get_current_user_optional`, `require_tier` |
| `backend/auth/rate_limits.py` | Free: 5 карт/день, 2 интерпретации/день |
| `backend/auth/router.py` | 7 эндпоинтов auth |

### Фаза 4.2 — Stripe (Дни 40–43)

| Файл | Назначение |
|------|------------|
| `backend/payments/__init__.py` | Пакет |
| `backend/payments/stripe_service.py` | Customer, Checkout, Portal, webhooks |
| `backend/payments/router.py` | 4 эндпоинта payments |

### Фаза 4.3 — Профиль пользователя (Дни 43–45)

| Файл | Назначение |
|------|------------|
| `backend/profile/__init__.py` | Пакет |
| `backend/profile/router.py` | Сохранённые карты, история, подписка, настройки |


## 3. Инструкция по установке и первому запуску

### Предварительные требования

- Python 3.11+
- Node.js 18+ и npm (для фронтенда)
- Docker и Docker Compose (для PostgreSQL)
- Git

### Шаг 1: Клонирование и настройка окружения

```bash
git clone <repo-url> astro-spa
cd astro-spa

# Создать .env из шаблона
cp .env.example .env
```

Отредактируйте `.env` — заполните обязательные поля:

```
JWT_SECRET=<сгенерируйте: python -c "import secrets; print(secrets.token_urlsafe(64))">
OPENAI_API_KEY=sk-...
```

### Шаг 2: Запуск PostgreSQL

```bash
docker compose up -d db
```

Дождитесь готовности (проверка: `docker compose logs db` — должно быть `ready to accept connections`).

### Шаг 3: Установка Python-зависимостей

```bash
python -m venv .venv
source .venv/bin/activate    # Linux/macOS
# .venv\Scripts\activate     # Windows

pip install -e ".[dev]"
```

### Шаг 4: Скачивание эфемеридных файлов

```bash
mkdir -p data/ephe
cd data/ephe
# Скачать с https://www.astro.com/ftp/swisseph/ephe/
# Минимум: sepl*.se1, semo*.se1, seas*.se1
# Или полный набор (~80 МБ)
cd ../..
```

### Шаг 5: Применение миграций

```bash
alembic upgrade head
```

### Шаг 6: Запуск бэкенда

```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

Проверка: `http://localhost:8000/health` → `{"status": "ok", ...}`

### Шаг 7: Запуск фронтенда (отдельный терминал)

```bash
cd frontend
npm install
npm run dev
```

Откроется `http://localhost:5173`.


## 4. Порядок запуска в разработке (ежедневная работа)

```bash
# Терминал 1 — база данных
docker compose up -d db

# Терминал 2 — бэкенд
source .venv/bin/activate
uvicorn backend.main:app --reload --port 8000

# Терминал 3 — фронтенд
cd frontend && npm run dev
```

Альтернативно через Makefile (если создан):

```bash
make dev    # запускает всё: db + backend + frontend
```

Или через Docker Compose целиком:

```bash
docker compose up       # db + api (с hot-reload через volume mount)
cd frontend && npm run dev   # фронтенд отдельно (Vite быстрее вне Docker)
```


## 5. Миграции базы данных (Alembic)

### Применить все миграции

```bash
alembic upgrade head
```

### Откатить последнюю миграцию

```bash
alembic downgrade -1
```

### Создать новую миграцию (autogenerate)

```bash
alembic revision --autogenerate -m "описание изменения"
```

Alembic автоматически сравнит текущие модели (`backend/models.py`) с состоянием БД и сгенерирует скрипт. Обязательно проверьте сгенерированный файл перед применением.

### Посмотреть текущую версию

```bash
alembic current
```

### Посмотреть историю миграций

```bash
alembic history --verbose
```

### Важно

- `alembic/env.py` читает `DATABASE_URL` из `backend/config.py` → из `.env`.
- Все модели импортируются в `env.py` через `import backend.models`.
- Запускайте `alembic` из корня проекта (где лежит `alembic.ini`).


## 6. Настройка внешних сервисов

### 6.1 OpenAI (GPT-4o)

1. Зарегистрируйтесь на https://platform.openai.com
2. Создайте API Key
3. В `.env`: `OPENAI_API_KEY=sk-...`

### 6.2 DeepSeek (fallback)

1. Зарегистрируйтесь на https://platform.deepseek.com
2. Создайте API Key
3. В `.env`: `DEEPSEEK_API_KEY=sk-...`

### 6.3 Google OAuth

1. Google Cloud Console → APIs & Services → Credentials
2. Create OAuth 2.0 Client ID (Web application)
3. Authorized redirect URIs: `http://localhost:5173/auth/google/callback`
4. В `.env`:
   ```
   GOOGLE_CLIENT_ID=xxxx.apps.googleusercontent.com
   GOOGLE_CLIENT_SECRET=GOCSPX-...
   ```

### 6.4 Stripe

1. Зарегистрируйтесь на https://stripe.com
2. Получите ключи в Dashboard → Developers → API keys
3. Создайте два Product с Price:
   - **Pro** (€7.99/мес, recurring) → скопируйте Price ID
   - **Premium** (€19.99/мес, recurring) → скопируйте Price ID
4. Настройте Webhook:
   - URL: `https://yourdomain.com/api/v1/payments/webhook`
   - Events: `checkout.session.completed`, `customer.subscription.updated`, `invoice.payment_failed`
   - Скопируйте Webhook signing secret
5. В `.env`:
   ```
   STRIPE_SECRET_KEY=sk_test_...
   STRIPE_WEBHOOK_SECRET=whsec_...
   STRIPE_PRICE_ID_PRO=price_...
   STRIPE_PRICE_ID_PREMIUM=price_...
   ```

### 6.5 Stripe CLI (для локального тестирования вебхуков)

```bash
# Установить: https://stripe.com/docs/stripe-cli
stripe login
stripe listen --forward-to localhost:8000/api/v1/payments/webhook
# Скопируйте whsec_... из вывода в .env
```


## 7. API-эндпоинты — полный список

### Health

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/health` | Статус приложения |
| GET | `/health/db` | Статус PostgreSQL |
| GET | `/health/ai` | Статус AI-провайдеров |

### Chart (Фазы 1, 3)

| Метод | Путь | Auth | Описание |
|-------|------|------|----------|
| POST | `/api/v1/chart/calculate` | Опционально | Рассчитать натальную карту |
| GET | `/api/v1/chart/{id}` | Нет | Получить сохранённую карту |
| GET | `/api/v1/chart/{id}/interpret` | Опционально | SSE-стриминг AI-интерпретации |
| POST | `/api/v1/chart/{id}/interpret` | Опционально | Полная интерпретация (не SSE) |
| GET | `/api/v1/chart/{id}/transits` | Опционально | Транзиты за период |

### Auth (Фаза 4.1)

| Метод | Путь | Auth | Описание |
|-------|------|------|----------|
| POST | `/api/v1/auth/register` | Нет | Регистрация email + пароль |
| POST | `/api/v1/auth/login` | Нет | Логин → JWT пара |
| POST | `/api/v1/auth/refresh` | Нет | Обновить access token |
| POST | `/api/v1/auth/google` | Нет | Google OAuth → JWT пара |
| GET | `/api/v1/auth/confirm-email?token=...` | Нет | Подтверждение email |
| GET | `/api/v1/auth/me` | Да | Профиль текущего пользователя |
| DELETE | `/api/v1/auth/me` | Да | Удалить аккаунт (GDPR) |

### Payments (Фаза 4.2)

| Метод | Путь | Auth | Описание |
|-------|------|------|----------|
| POST | `/api/v1/payments/checkout` | Да | Создать Stripe Checkout сессию |
| POST | `/api/v1/payments/portal` | Да | Открыть Stripe Customer Portal |
| GET | `/api/v1/payments/subscription` | Да | Текущая подписка |
| POST | `/api/v1/payments/webhook` | Нет (Stripe sig) | Stripe webhook |

### Profile (Фаза 4.3)

| Метод | Путь | Auth | Описание |
|-------|------|------|----------|
| GET | `/api/v1/profile/me` | Да | Полный профиль + статистика + фичи тира |
| GET | `/api/v1/profile/charts` | Да | Список сохранённых карт (pagination) |
| POST | `/api/v1/profile/charts/{id}/label` | Да | Установить метку на карту |
| DELETE | `/api/v1/profile/charts/{id}` | Да | Удалить карту |
| GET | `/api/v1/profile/interpretations` | Да | История интерпретаций |
| GET | `/api/v1/profile/interpretations/{id}` | Да | Полный текст интерпретации |
| GET | `/api/v1/profile/subscription` | Да | Подписка + фичи тира |
| PUT | `/api/v1/profile/settings` | Да | Сменить email / пароль |


## 8. Тестирование

### Запуск тестов

```bash
# Все тесты
pytest

# С покрытием
pytest --cov=backend --cov-report=html

# Только определённый модуль
pytest backend/tests/test_auth.py -v
```

### Тестирование API вручную (curl)

```bash
# Регистрация
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "Secret123"}'

# Логин
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "Secret123"}'
# → {"access_token": "eyJ...", "refresh_token": "eyJ...", ...}

# Расчёт карты (с авторизацией)
curl -X POST http://localhost:8000/api/v1/chart/calculate \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer eyJ..." \
  -d '{"birth_date": "1990-06-15", "birth_time": "14:30", "birth_place": "Moscow"}'

# Мои карты
curl http://localhost:8000/api/v1/profile/charts \
  -H "Authorization: Bearer eyJ..."

# Создать Checkout-сессию
curl -X POST http://localhost:8000/api/v1/payments/checkout \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer eyJ..." \
  -d '{"tier": "pro", "success_url": "http://localhost:5173/success", "cancel_url": "http://localhost:5173/pricing"}'
```

### Swagger UI

Откройте `http://localhost:8000/docs` — интерактивная документация FastAPI со всеми эндпоинтами. Кнопка «Authorize» позволяет ввести Bearer token.


## 9. Деплой в production (Фаза 5 — краткая сводка)

### Docker build

```bash
docker build -t astro-spa .
```

### Railway / Render

1. Подключить GitHub-репозиторий
2. Добавить managed PostgreSQL
3. Задать переменные окружения (все из `.env.example`)
4. Настроить домен + SSL (автоматически через платформу)

### Переменные окружения (production)

```
DATABASE_URL=postgresql://...  (от платформы)
JWT_SECRET=<длинный случайный>
OPENAI_API_KEY=sk-...
STRIPE_SECRET_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_ID_PRO=price_...
STRIPE_PRICE_ID_PREMIUM=price_...
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
CORS_ORIGINS=["https://yourdomain.com"]
DEBUG=false
```

### Важные настройки production

- `DEBUG=false`
- `JWT_SECRET` — длинная случайная строка, не `CHANGE-ME-IN-PRODUCTION`
- `CORS_ORIGINS` — только ваш домен, не `*`
- Stripe: переключить с `sk_test_` на `sk_live_`
- Google OAuth: добавить production redirect URI
