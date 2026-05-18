# Astro SPA — Полная структура проекта и руководство по деплою
*Обновлено: апрель 2026. Актуальная версия с учётом всех изменений и деплоя.*

---

## 1. Инфраструктура (Production)

| Компонент | Платформа | URL |
|---|---|---|
| **Фронтенд** | Vercel (бесплатно) | https://astro-qnbq.vercel.app |
| **Бэкенд API** | Railway | https://astro-production-e070.up.railway.app |
| **PostgreSQL** | Railway (в том же проекте) | внутренний адрес через `${{Postgres.DATABASE_URL}}` |
| **Репозиторий** | GitHub | https://github.com/alex753ad/astro |

### Деплой
- **Бэкенд**: Railway автоматически деплоит при каждом `git push` в `main` через `Dockerfile`
- **Фронтенд**: Vercel деплоит при каждом `git push` в `main`, берёт готовый `frontend/dist/`
- **Сборка фронтенда**: выполняется локально (`npm run build`), результат коммитится в `frontend/dist/`

---

## 2. Дерево файлов

```
astro/                                   # Корень репозитория
├── backend/
│   ├── __init__.py
│   ├── main.py                          # Точка входа FastAPI. Все эндпоинты.
│   │                                    # Загружает .env через load_dotenv().
│   ├── config.py                        # Pydantic Settings. Читает все env-переменные.
│   │                                    # Поле: database_url (читает DATABASE_URL из env)
│   ├── database.py                      # SQLAlchemy engine, SessionLocal, Base, get_db.
│   │                                    # Использует settings.database_url (из env, не захардкожен)
│   ├── models.py                        # ORM-модели БД:
│   │                                    #   User, NatalChart, Interpretation, Subscription
│   ├── schemas.py                       # Pydantic-схемы запросов и ответов
│   ├── cache.py                         # In-memory TTL-кэш (thread-safe dict)
│   │
│   ├── ephemeris/                       # Ядро астрологических расчётов
│   │   ├── __init__.py
│   │   ├── calculator.py                # pyswisseph обёртка
│   │   ├── aspects.py                   # Расчёт аспектов между планетами
│   │   ├── houses.py                    # Системы домов (Плацидус, Кох, Equal, Whole Sign)
│   │   └── geo.py                       # Nominatim геокодирование, timezonefinder, DST
│   │
│   ├── interpretation/                  # AI-интерпретация натальной карты
│   │   ├── __init__.py
│   │   ├── base.py                      # ABC: InterpretationEngine
│   │   ├── router.py                    # Fallback-цепочка: GPT-4o → DeepSeek → шаблоны
│   │   ├── gpt4o.py                     # GPT-4o реализация (httpx + SSE)
│   │   ├── deepseek.py                  # DeepSeek V3 fallback
│   │   ├── template.py                  # Шаблонный движок без LLM
│   │   ├── prompts.py                   # Промпты для натальной карты
│   │   └── knowledge_base.json          # 300–500 записей интерпретаций
│   │
│   ├── transit/                         # Транзиты планет
│   │   ├── __init__.py
│   │   ├── engine.py                    # Расчётный движок транзитов
│   │   ├── prompts.py                   # Промпты для интерпретации транзита
│   │   └── forecast_prompt.py           # Промпты для прогнозов (дневной, месячный)
│   │
│   ├── auth/                            # Аутентификация
│   │   ├── __init__.py
│   │   ├── jwt.py                       # JWT: access (15 мин), refresh (7 дней)
│   │   ├── passwords.py                 # bcrypt через passlib
│   │   ├── oauth.py                     # Google OAuth 2.0
│   │   ├── dependencies.py              # FastAPI Depends: get_current_user, require_tier
│   │   ├── rate_limits.py               # tier_limiter, check_chart_limit
│   │   └── router.py                    # /auth/register, login, refresh, google, me
│   │
│   ├── payments/                        # Stripe
│   │   ├── __init__.py
│   │   ├── stripe_service.py            # Customer, Checkout, Portal, webhooks
│   │   └── router.py                    # /payments/checkout, portal, webhook, subscription
│   │
│   ├── profile/                         # Профиль пользователя
│   │   ├── __init__.py
│   │   └── router.py                    # /profile/charts, interpretations, subscription
│   │
│   └── tests/
│       ├── conftest.py
│       ├── test_ephemeris.py
│       ├── test_transits.py
│       ├── test_auth.py
│       └── test_payments.py
│
├── frontend/
│   ├── src/
│   │   ├── api/
│   │   │   └── client.js                # API клиент. API_BASE = Railway URL (абсолютный).
│   │   │                                # Все fetch-запросы идут напрямую на Railway.
│   │   ├── pages/
│   │   │   ├── ChartPage.jsx            # Главная страница карты. API_BASE захардкожен
│   │   │   │                            # на Railway URL (не относительный путь).
│   │   │   └── HomePage.jsx             # Форма BirthForm → calculateChart() → redirect
│   │   │
│   │   └── components/
│   │       ├── NatalChart.jsx           # D3.js SVG натальное колесо
│   │       ├── TransitTimeline.jsx      # Временная шкала транзитов.
│   │       │                            # fetch → Railway URL (абсолютный)
│   │       ├── ForecastScale.jsx        # Планировщик день/неделя/месяц.
│   │       │                            # fetch → Railway URL (абсолютный)
│   │       ├── AstroCalendar.jsx        # Астро-календарь.
│   │       │                            # fetch → Railway URL (абсолютный)
│   │       ├── Interpretation.jsx       # SSE-стриминг AI-интерпретации
│   │       ├── BirthForm.jsx            # Форма: дата, время, место рождения
│   │       ├── ChartSummary.jsx         # Таблица планет по знакам и домам
│   │       ├── AspectTable.jsx          # Таблица аспектов натальной карты
│   │       └── client.js                # Копия api/client.js (дублирует Railway URL)
│   │
│   ├── dist/                            # Собранный фронтенд (коммитится в git!)
│   │   ├── index.html                   # Ссылается на актуальный JS бандл
│   │   └── assets/
│   │       ├── index-*.js               # Vite бандл (имя меняется при каждой сборке)
│   │       └── index-*.css
│   │
│   ├── package.json
│   ├── vite.config.js                   # proxy только для dev-режима (localhost:8000)
│   └── vercel.json                      # SPA роутинг: routes → filesystem → index.html
│
├── data/
│   └── ephe/                            # Swiss Ephemeris файлы (~3 МБ, в git)
│       ├── seas_18.se1
│       ├── semo_18.se1
│       └── sepl_18.se1
│
├── alembic/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│       ├── 001_baseline.py
│       ├── 002_phase4_auth_payments.py
│       └── 003_users_auth_stripe.py     # Текущая head-версия
│
├── vercel.json                          # Корневой vercel.json (SPA роутинг)
├── docker-compose.yml                   # PostgreSQL 16-alpine (только для dev)
├── Dockerfile                           # Production сборка для Railway
│                                        # COPY data/ephe/ /app/data/ephe/
│                                        # CMD uvicorn backend.main:app --host 0.0.0.0 --port 8000
├── pyproject.toml
├── alembic.ini
├── .env                                 # Секреты (НЕ в git)
└── .gitignore                           # Исключает: .env, .venv, __pycache__, node_modules
                                         # НЕ исключает: data/ephe/, frontend/dist/
```

---

## 3. Переменные окружения Railway (Production)

### Сервис: astro (бэкенд)

| Переменная | Значение | Примечание |
|---|---|---|
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` | Ссылка на внутренний URL Postgres |
| `EPHE_PATH` | `/app/data/ephe` | Путь к эфемеридам в контейнере |
| `JWT_SECRET` | `<64 символа>` | Сгенерирован случайно |
| `JWT_ALGORITHM` | `HS256` | |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `15` | |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | `7` | |
| `OPENAI_API_KEY` | `sk-proj-...` | GPT-4o |
| `DEEPSEEK_API_KEY` | `sk-...` | Fallback |
| `AI_DAILY_BUDGET_USD` | `10.0` | |
| `RATE_LIMIT_ANON` | `30/minute` | |
| `RATE_LIMIT_AUTH` | `100/minute` | |
| `RATE_LIMIT_FREE_CHARTS_PER_DAY` | `5` | |
| `RATE_LIMIT_FREE_INTERPRETATIONS_PER_DAY` | `2` | |
| `STRIPE_SECRET_KEY` | `sk_test_...` | |
| `STRIPE_WEBHOOK_SECRET` | `whsec_...` | |
| `DEBUG` | `false` | |
| `CORS_ORIGINS` | `["https://astro-qnbq.vercel.app"]` | |

### Сервис: Postgres-E7GD
Railway автоматически управляет переменными PostgreSQL. `DATABASE_URL` доступен через `${{Postgres.DATABASE_URL}}`.

---

## 4. Все API-эндпоинты

### Health
| Метод | Путь | Описание |
|---|---|---|
| GET | `/health` | Статус приложения |
| GET | `/health/db` | Статус PostgreSQL |
| GET | `/health/ai` | Статус AI-провайдеров |

### Chart
| Метод | Путь | Описание |
|---|---|---|
| POST | `/api/v1/chart/calculate` | Рассчитать натальную карту |
| GET | `/api/v1/chart/{id}` | Получить сохранённую карту |
| GET | `/api/v1/chart/{id}/interpret` | SSE-стриминг AI-интерпретации |
| POST | `/api/v1/chart/{id}/interpret` | Полная интерпретация (не SSE) |
| GET | `/api/v1/chart/{id}/pdf` | Скачать PDF карты |

### Transits
| Метод | Путь | Описание |
|---|---|---|
| GET | `/api/v1/chart/{id}/transits` | Список транзитов за период |
| GET | `/api/v1/chart/{id}/transits/positions` | Позиции планет на дату |
| GET | `/api/v1/chart/{id}/transits/interpret` | SSE обзор периода |
| POST | `/api/v1/chart/{id}/transits/event/interpret` | SSE интерпретация события |

### Forecast
| Метод | Путь | Описание |
|---|---|---|
| GET | `/api/v1/chart/{id}/forecast/daily` | Прогноз на день |
| GET | `/api/v1/chart/{id}/forecast/weekly` | Прогноз на неделю |
| GET | `/api/v1/chart/{id}/forecast/monthly` | Прогноз на месяц |

### Auth
| Метод | Путь | Описание |
|---|---|---|
| POST | `/api/v1/auth/register` | Регистрация |
| POST | `/api/v1/auth/login` | Логин → JWT |
| POST | `/api/v1/auth/refresh` | Обновить токен |
| POST | `/api/v1/auth/google` | Google OAuth |
| GET | `/api/v1/auth/me` | Текущий пользователь |

### Payments / Profile
| Метод | Путь | Описание |
|---|---|---|
| POST | `/api/v1/payments/checkout` | Stripe Checkout |
| POST | `/api/v1/payments/webhook` | Stripe webhook |
| GET | `/api/v1/profile/charts` | Сохранённые карты |
| GET | `/api/v1/profile/interpretations` | История интерпретаций |

---

## 5. Как обновить приложение

### Обновить бэкенд
```bash
# Внеси изменения в backend/
git add backend/
git commit -m "feat: описание изменений"
git push
# Railway автоматически пересоберёт и задеплоит
```

### Обновить фронтенд
```bash
# Внеси изменения в frontend/src/
cd frontend
npm run build          # Собрать dist/
cd ..
git add frontend/src/ frontend/dist/
git commit -m "feat: описание изменений"
git push
# Vercel автоматически задеплоит новый dist/
```

### Важно при изменении API URL
Если URL бэкенда изменится — нужно обновить в **4 местах**:
1. `frontend/src/api/client.js` — константа `API_BASE`
2. `frontend/src/components/client.js` — константа `API_BASE`
3. `frontend/src/pages/ChartPage.jsx` — константа `API_BASE`
4. `frontend/src/components/TransitTimeline.jsx` — все fetch-вызовы
5. `frontend/src/components/ForecastScale.jsx` — все fetch-вызовы
6. `frontend/src/components/AstroCalendar.jsx` — fetch-вызов

---

## 6. Безопасность

| Что защищено | Как |
|---|---|
| Пароли | bcrypt через passlib |
| Сессии | JWT (access 15 мин, refresh 7 дней) |
| Rate limiting | 30 req/min анонимы, 100 req/min авторизованные |
| CORS | Только `https://astro-qnbq.vercel.app` |
| Секреты | В переменных Railway, не в коде |
| БД пароль | Через `${{Postgres.DATABASE_URL}}`, не захардкожен |
| DEBUG | `false` в production |

---

## 7. Быстрый поиск при ошибках

| Симптом | Где искать |
|---|---|
| Бэкенд не стартует | Railway → Deployments → логи |
| `swe.Error` / планеты не считаются | `data/ephe/*.se1` файлы, `EPHE_PATH=/app/data/ephe` |
| БД не подключается | Railway → Variables → `DATABASE_URL = ${{Postgres.DATABASE_URL}}` |
| CORS ошибки | Railway → `CORS_ORIGINS` → точный URL Vercel |
| SSE не стримит | Заголовок `X-Accel-Buffering: no` в ответе |
| Фронтенд показывает старую версию | Пересобрать: `npm run build` → закоммитить `dist/` |
| 404 на API с фронтенда | Проверить `API_BASE` во всех 6 файлах фронтенда |
| JWT ошибки | Railway → `JWT_SECRET` установлен и не пустой |
| Прогноз 503 | Railway → `OPENAI_API_KEY` или `DEEPSEEK_API_KEY` установлены |
