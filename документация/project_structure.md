# Astro SPA — Полная структура проекта и руководство по деплою

---

## 1. Дерево файлов (актуальное)

```
astro-spa/
├── backend/
│   ├── __init__.py
│   ├── main.py                          # Точка входа FastAPI. Все эндпоинты.
│   │                                    # Загружает .env через load_dotenv().
│   ├── config.py                        # Pydantic Settings. Читает все env-переменные.
│   ├── database.py                      # SQLAlchemy engine, SessionLocal, Base, get_db.
│   ├── models.py                        # ORM-модели БД:
│   │                                    #   User, NatalChart, Interpretation, Subscription
│   ├── schemas.py                       # Pydantic-схемы запросов и ответов:
│   │                                    #   BirthDataInput, NatalChartResponse,
│   │                                    #   TransitEvent, TransitResponse,
│   │                                    #   TransitPlanetPosition, TransitPlanetPositionsResponse,
│   │                                    #   PlanetPosition, HouseData, AspectData, PointData,
│   │                                    #   Auth/Payment/Profile схемы
│   ├── cache.py                         # In-memory TTL-кэш (thread-safe dict).
│   │                                    #   Экспортирует: interpretation_cache, transit_cache,
│   │                                    #   make_profile_hash()
│   │
│   ├── ephemeris/                       # Ядро астрологических расчётов
│   │   ├── __init__.py
│   │   ├── calculator.py                # pyswisseph обёртка.
│   │   │                                #   Экспортирует: PLANETS dict, ZODIAC_SIGNS list,
│   │   │                                #   _datetime_to_jd(), _longitude_to_sign(),
│   │   │                                #   _calc_planet_position() [lru_cache],
│   │   │                                #   calculate_full_chart(), calculate_planets(),
│   │   │                                #   calculate_houses(), assign_houses()
│   │   ├── aspects.py                   # Расчёт аспектов между планетами.
│   │   │                                #   Экспортирует: ASPECTS dict {"conjunction": 0.0, ...},
│   │   │                                #   _angular_distance(), calculate_aspects(),
│   │   │                                #   AspectResult dataclass
│   │   ├── houses.py                    # Системы домов (Плацидус, Кох, Equal, Whole Sign)
│   │   └── geo.py                       # Nominatim геокодирование, timezonefinder, DST.
│   │                                    #   Экспортирует: geocode_place(), resolve_utc_datetime(),
│   │                                    #   validate_coordinates(), GeocodingError, AmbiguousTimeError
│   │
│   ├── interpretation/                  # AI-интерпретация натальной карты
│   │   ├── __init__.py
│   │   ├── base.py                      # ABC: InterpretationEngine, InterpretationRequest/Result
│   │   ├── router.py                    # Fallback-цепочка: GPT-4o → DeepSeek → шаблоны.
│   │   │                                #   Экспортирует: get_router()
│   │   ├── gpt4o.py                     # GPT-4o реализация (httpx + SSE)
│   │   ├── deepseek.py                  # DeepSeek V3 fallback
│   │   ├── template.py                  # Шаблонный движок без LLM
│   │   ├── prompts.py                   # Промпты для натальной карты.
│   │   │                                #   Экспортирует: _compact_profile()  ← используется
│   │   │                                #   в transit/prompts.py и transit/forecast_prompt.py
│   │   └── knowledge_base.json          # 300–500 записей интерпретаций (шаблонный fallback)
│   │
│   ├── transit/                         # Транзиты планет
│   │   ├── __init__.py                  # Пустой инициализатор пакета
│   │   ├── engine.py                    # Расчётный движок транзитов.
│   │   │                                #   Модель данных: один TransitEvent = весь период
│   │   │                                #   активности аспекта (start_date/peak_date/end_date).
│   │   │                                #   Экспортирует:
│   │   │                                #     calculate_transits(natal_planets, from_date, to_date)
│   │   │                                #     get_active_transits(events, on_date)
│   │   │                                #     get_planet_positions_for_date(query_date)
│   │   │                                #     get_transit_summary(events)
│   │   │                                #     TransitEvent dataclass
│   │   │                                #   Константы: TRANSIT_ORBS, FAST_PLANETS, SLOW_PLANETS,
│   │   │                                #     FAST_STEP_HOURS=4, SLOW_STEP_HOURS=24
│   │   ├── prompts.py                   # Промпты для интерпретации отдельного события.
│   │   │                                #   Экспортирует:
│   │   │                                #     build_transit_event_prompt()
│   │   │                                #     build_transit_period_prompt()
│   │   │                                #     get_template_transit_text()  ← fallback без AI
│   │   │                                #     TRANSIT_TEMPLATES dict
│   │   └── forecast_prompt.py           # Промпты для прогнозов (дневной, месячный, события).
│   │                                    #   Экспортирует:
│   │                                    #     build_daily_forecast_prompt()
│   │                                    #     build_monthly_forecast_prompt()
│   │                                    #     build_important_events_prompt()
│   │                                    #     parse_forecast_response()  ← парсит JSON из AI
│   │                                    #   Промпты возвращают строгий JSON-ответ от AI:
│   │                                    #     DAILY: potential_score, summary, do_today,
│   │                                    #       avoid_today, spheres(7), morning_ritual
│   │                                    #     MONTHLY: month_summary, key_themes, best_dates,
│   │                                    #       caution_dates, spheres(7), month_affirmation
│   │
│   ├── auth/                            # Аутентификация
│   │   ├── __init__.py
│   │   ├── jwt.py                       # JWT: access (15 мин), refresh (7 дней)
│   │   ├── passwords.py                 # bcrypt через passlib
│   │   ├── oauth.py                     # Google OAuth 2.0
│   │   ├── dependencies.py              # FastAPI Depends:
│   │   │                                #   get_current_user, get_current_user_optional,
│   │   │                                #   require_tier
│   │   ├── rate_limits.py               # tier_limiter, check_chart_limit
│   │   └── router.py                    # /auth/register, login, refresh, google, confirm, me
│   │
│   ├── payments/                        # Stripe
│   │   ├── __init__.py
│   │   ├── stripe_service.py            # Customer, Checkout, Portal, webhooks
│   │   └── router.py                    # /payments/checkout, portal, webhook, subscription
│   │
│   ├── profile/                         # Профиль пользователя
│   │   ├── __init__.py
│   │   └── router.py                    # /profile/charts, interpretations, subscription, settings
│   │
│   └── tests/
│       ├── conftest.py
│       ├── test_ephemeris.py
│       ├── test_transits.py
│       ├── test_auth.py
│       └── test_payments.py
│
├── frontend/
│   └── src/
│       ├── pages/
│       │   ├── ChartPage.jsx            # Главная страница карты.
│       │   │                            #   State: chart, transitPlanets, showForecast.
│       │   │                            #   handleDateSelect(date, dayEvents, positions)
│       │   │                            #     → передаёт позиции всех планет в NatalChart.
│       │   │                            #   Рендерит: NatalChart + ChartSummary + AspectTable
│       │   │                            #     + Interpretation + TransitTimeline (full-width).
│       │   └── HomePage.jsx             # Форма BirthForm → POST /chart/calculate → redirect.
│       │
│       └── components/
│           ├── NatalChart.jsx           # D3.js SVG натальное колесо.
│           │                            #   Props: planets, houses, aspects, ascendant,
│           │                            #     midheaven, timeUnknown, transitPlanets[].
│           │                            #   transitPlanets[] → внешнее кольцо:
│           │                            #     все планеты (яркость = есть аспект),
│           │                            #     линии аспектов к натальным планетам,
│           │                            #     ℞ для ретроградных.
│           │                            #   ViewBox расширяется при наличии transitPlanets.
│           ├── TransitTimeline.jsx      # Временная шкала транзитов.
│           │                            #   Props: chartId, onDateSelect(date,events,positions).
│           │                            #   Загрузка: GET /transits?from_date&to_date (2 месяца).
│           │                            #   Фильтры: планеты, аспекты, орб.
│           │                            #   При клике на дату:
│           │                            #     1. Фильтр: start_date ≤ activeDate ≤ end_date
│           │                            #     2. GET /transits/positions?on_date → реальные lon
│           │                            #     3. Вызов onDateSelect → NatalChart обновляется
│           │                            #     4. Кнопка "✦ Прогноз на этот день"
│           │                            #   InterpretationPanel: POST /transits/event/interpret
│           │                            #     → SSE стриминг текста интерпретации.
│           │                            #   ForecastPanel: GET /forecast/daily?on_date
│           │                            #     → JSON прогноз с вкладками Обзор/Сферы/Советы.
│           ├── Interpretation.jsx       # SSE-стриминг AI-интерпретации натальной карты.
│           │                            #   GET /chart/{id}/interpret → текст чанками.
│           ├── BirthForm.jsx            # Форма: дата, время, место рождения.
│           ├── ChartSummary.jsx         # Таблица планет по знакам и домам.
│           └── AspectTable.jsx          # Таблица аспектов натальной карты.
│
├── alembic/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│       ├── 001_baseline.py             # User, NatalChart, Interpretation
│       ├── 002_phase4_auth_payments.py  # Auth-поля, Subscription
│       └── 003_users_auth_stripe.py    # Текущая head-версия
│
├── data/
│   └── ephe/                           # Swiss Ephemeris файлы (.se1, ~80 МБ)
│                                       # ОБЯЗАТЕЛЬНО: seas_18.se1, semo_18.se1, sepl_18.se1
│
├── docker-compose.yml                  # PostgreSQL 16-alpine (dev)
├── Dockerfile                          # Multi-stage build (production)
├── pyproject.toml                      # Python зависимости
├── alembic.ini
├── Makefile
├── .env                                # Секреты (НЕ в git)
└── .env.example                        # Шаблон

```

---

## 2. Все API-эндпоинты

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
| Метод | Путь | Query-параметры | Описание |
|---|---|---|---|
| GET | `/api/v1/chart/{id}/transits` | `from_date, to_date, planet?, max_orb?` | Список транзитов (периоды) |
| GET | `/api/v1/chart/{id}/transits/positions` | `on_date` | Позиции всех планет на дату |
| GET | `/api/v1/chart/{id}/transits/interpret` | `from_date, to_date` | SSE обзор периода |
| POST | `/api/v1/chart/{id}/transits/event/interpret` | — | SSE интерпретация одного события |

### Forecast
| Метод | Путь | Query-параметры | Описание |
|---|---|---|---|
| GET | `/api/v1/chart/{id}/forecast/daily` | `on_date` | JSON прогноз на день (AI) |
| GET | `/api/v1/chart/{id}/forecast/monthly` | `from_date, to_date` | JSON прогноз на месяц (AI) |

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

## 3. Поток данных — ключевые сценарии

### Расчёт карты
```
BirthForm → POST /chart/calculate
  → geo.py: geocode_place() → lat/lon/timezone
  → calculator.py: calculate_full_chart()
      → _calc_planet_position() [lru_cache по JD]
      → calculate_houses()
      → aspects.py: calculate_aspects()
  → NatalChart сохраняется в PostgreSQL
  → redirect /chart/{id}
  → ChartPage загружает карту → NatalChart.jsx рендерит SVG
```

### Транзиты + прогноз дня
```
TransitTimeline монтируется с chartId
  → GET /transits?from_date&to_date (текущий + следующий месяц)
  → engine.py: calculate_transits()
      → один TransitEvent = весь период (start_date/peak_date/end_date)
      → _find_exact_aspect() бисекция ±5 мин
  → Пользователь кликает дату в DateNav
  → filter: start_date ≤ date ≤ end_date (активные транзиты)
  → GET /transits/positions?on_date
      → engine.py: get_planet_positions_for_date()
  → onDateSelect(date, events, positions) → ChartPage
      → NatalChart.jsx: внешнее кольцо с реальными lon всех планет
  → Кнопка "Прогноз на этот день"
  → GET /forecast/daily?on_date
      → engine.py: get_active_transits() для ±1 день
      → forecast_prompt.py: build_daily_forecast_prompt()
      → Claude API / OpenAI → JSON
      → parse_forecast_response()
      → ForecastPanel: Обзор / Сферы / Советы
```

### SSE интерпретация транзита
```
Пользователь кликает EventCard в TransitTimeline
  → POST /transits/event/interpret {transit_planet, natal_planet, aspect_type}
  → transit/prompts.py: get_template_transit_text() (fallback)
  → interpretation/router.py: GPT-4o → DeepSeek → шаблон
  → SSE stream → InterpretationPanel (читает чанками через ReadableStream)
```

---

## 4. Переменные окружения (.env)

```env
# База данных
DATABASE_URL=postgresql://astro:astro@localhost:5432/astro

# Эфемериды
EPHE_PATH=./data/ephe

# JWT
JWT_SECRET=<длинная случайная строка>

# AI (хотя бы один обязателен для прогнозов)
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-proj-...
DEEPSEEK_API_KEY=sk-...

# Google OAuth (опционально)
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=

# Stripe (опционально)
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_ID_PRO=price_...
STRIPE_PRICE_ID_PREMIUM=price_...

# CORS
CORS_ORIGINS=["http://localhost:5173"]
DEBUG=true
```

---

## 5. Варианты бесплатного хостинга

### Вариант А — Railway (рекомендую)

**Бесплатно:** $5 кредитов в месяц (хватает для небольшого трафика).
**Подходит:** полный стек — backend + PostgreSQL в одном месте.

**Шаги:**

1. Зарегистрируйся на [railway.app](https://railway.app)
2. Создай новый проект → **Deploy from GitHub** → подключи репозиторий
3. Добавь PostgreSQL: **New** → **Database** → **PostgreSQL**
4. В настройках сервиса укажи переменные окружения (все из `.env`)
5. В `DATABASE_URL` вставь строку подключения из Railway PostgreSQL (она генерируется автоматически)
6. Загрузи файлы эфемерид в репозиторий в папку `data/ephe/` (или настрой Volume)
7. Railway автоматически запустит `Dockerfile`

**Dockerfile** (уже есть в проекте) должен содержать:
```dockerfile
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Фронтенд** — задеплой отдельно на Vercel (бесплатно, без ограничений):
- `npm run build` → папка `dist/`
- В `vite.config.js` настрой proxy на URL Railway backend

---

### Вариант Б — Render

**Бесплатно:** Web Service засыпает через 15 мин неактивности (первый запрос медленный).
**PostgreSQL:** бесплатная БД на 90 дней, потом платно.

**Шаги:**

1. Зарегистрируйся на [render.com](https://render.com)
2. **New** → **Web Service** → подключи GitHub
3. Build Command: `pip install -e .`
4. Start Command: `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
5. **New** → **PostgreSQL** → скопируй `DATABASE_URL` в переменные сервиса
6. Добавь все переменные окружения в **Environment**
7. Фронтенд: **New** → **Static Site** → Build: `npm run build`, Publish: `dist`

---

### Вариант В — Fly.io

**Бесплатно:** 3 shared-CPU машины, 256 МБ RAM (маловато для pyswisseph + AI).
**Лучше:** для экспериментов, не для постоянной работы.

---

### Итоговая рекомендация

| Платформа | Backend | PostgreSQL | Фронтенд | Сложность |
|---|---|---|---|---|
| **Railway + Vercel** | Railway (бесплатно) | Railway (бесплатно) | Vercel (бесплатно) | ★★☆ |
| **Render** | Render (засыпает) | Render (90 дней) | Render Static | ★☆☆ |
| **Fly.io** | Fly.io | Supabase (бесплатно) | Vercel | ★★★ |

**Оптимально:** Railway для backend + PostgreSQL, Vercel для фронтенда.

---

## 6. Подготовка к деплою — чеклист

```bash
# 1. Убедиться что .gitignore содержит:
.env
.venv/
__pycache__/
*.pyc
data/ephe/*.se1   # НЕ коммитить эфемериды (80 МБ) — загрузить отдельно

# 2. Собрать фронтенд
cd frontend && npm run build

# 3. Проверить Dockerfile
docker build -t astro-spa . && docker run -p 8000:8000 astro-spa

# 4. Проверить что alembic работает с production DATABASE_URL
DATABASE_URL=postgresql://... alembic upgrade head

# 5. Сменить в .env (production):
DEBUG=false
CORS_ORIGINS=["https://your-frontend.vercel.app"]
JWT_SECRET=<новый длинный секрет>
STRIPE_SECRET_KEY=sk_live_...  # если используешь Stripe
```

---

## 7. Быстрый поиск при ошибках

| Симптом | Где искать |
|---|---|
| `ModuleNotFoundError` | Проверь `backend/transit/__init__.py` существует |
| `swe.Error` / планеты не считаются | `data/ephe/*.se1` файлы отсутствуют |
| Транзитов 0 или мало | `engine.py` → `TRANSIT_ORBS`, проверь `start_date ≤ date ≤ end_date` |
| SSE не стримит | Nginx/proxy буферизует → заголовок `X-Accel-Buffering: no` |
| Прогноз 503 | `.env` не загружен → `load_dotenv()` в `main.py`, проверь `OPENAI_API_KEY` |
| PDF ошибка кириллицы | `main.py` → `Content-Disposition` → RFC 5987 `filename*=UTF-8''...` |
| Чёрный экран после карты | `TransitTimeline.jsx` → ключи событий используют `peak_date`, не `date` |
| `database: error` | Docker не запущен → `docker compose up -d db` |
| JWT ошибки | `auth/jwt.py` → проверь `JWT_SECRET` в `.env` |
