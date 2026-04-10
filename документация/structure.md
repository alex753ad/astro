# Astro SPA — Структура проекта (актуальная, Фаза 3)

## Дерево файлов

```
astro-spa/
├── backend/
│   ├── __init__.py
│   ├── main.py                        # FastAPI app — все роутеры + транзитные эндпоинты
│   ├── config.py                      # Pydantic Settings — env-переменные
│   ├── database.py                    # SQLAlchemy engine, SessionLocal, Base, get_db
│   ├── models.py                      # ORM: User, NatalChart, Interpretation, Subscription
│   ├── schemas.py                     # Pydantic-схемы (BirthDataInput, TransitRequest,
│   │                                  #   TransitEvent, TransitResponse, NatalChartResponse…)
│   ├── cache.py                       # In-memory TTL-кэш (interpretation_cache, transit_cache)
│   │
│   ├── ephemeris/                     # Фаза 1 — расчётное ядро
│   │   ├── __init__.py
│   │   ├── calculator.py              # pyswisseph: позиции планет, дома, ASC/MC
│   │   │                              #   экспортирует: PLANETS, ZODIAC_SIGNS,
│   │   │                              #   _datetime_to_jd, _longitude_to_sign,
│   │   │                              #   _calc_planet_position, calculate_full_chart
│   │   ├── aspects.py                 # Аспекты: ASPECTS dict, _angular_distance,
│   │   │                              #   calculate_aspects, AspectResult
│   │   ├── houses.py                  # Системы домов (Плацидус, Кох, Equal, Whole Sign)
│   │   └── geo.py                     # Nominatim геокодирование, timezonefinder, DST
│   │
│   ├── interpretation/                # Фаза 2 — AI-интерпретация
│   │   ├── __init__.py
│   │   ├── base.py                    # InterpretationEngine ABC, InterpretationRequest
│   │   ├── router.py                  # Fallback-цепочка: GPT-4o → DeepSeek → шаблоны
│   │   ├── gpt4o.py                   # GPT-4o через httpx + SSE
│   │   ├── deepseek.py                # DeepSeek V3 fallback
│   │   ├── template.py                # Шаблонный движок без LLM
│   │   ├── prompts.py                 # Промпты для натальной карты + _compact_profile()
│   │   └── knowledge_base.json        # 300–500 записей интерпретаций
│   │
│   ├── transit/                       # Фаза 3 — транзиты  ← НОВОЕ
│   │   ├── __init__.py                # Инициализация пакета (пустой)
│   │   ├── engine.py                  # Расчёт транзитов: calculate_transits(),
│   │   │                              #   _find_exact_aspect(), get_transit_summary()
│   │   │                              #   Классы: TransitEvent (dataclass)
│   │   │                              #   Константы: FAST_PLANETS, SLOW_PLANETS,
│   │   │                              #   TRANSIT_ORBS, FAST_STEP_HOURS, SLOW_STEP_HOURS
│   │   └── prompts.py                 # Промпты и шаблоны для транзитов:
│   │                                  #   build_transit_event_prompt()
│   │                                  #   build_transit_period_prompt()
│   │                                  #   get_template_transit_text()
│   │                                  #   TRANSIT_TEMPLATES dict
│   │
│   ├── auth/                          # Фаза 4.1 — аутентификация
│   │   ├── __init__.py
│   │   ├── jwt.py
│   │   ├── passwords.py
│   │   ├── oauth.py
│   │   ├── dependencies.py            # get_current_user, get_current_user_optional,
│   │   │                              #   require_tier
│   │   ├── rate_limits.py             # tier_limiter, check_chart_limit
│   │   └── router.py
│   │
│   ├── payments/                      # Фаза 4.2 — Stripe
│   │   ├── __init__.py
│   │   ├── stripe_service.py
│   │   └── router.py
│   │
│   ├── profile/                       # Фаза 4.3 — профиль
│   │   ├── __init__.py
│   │   └── router.py
│   │
│   └── tests/
│       ├── __init__.py
│       ├── test_ephemeris.py
│       ├── test_transits.py           # Тесты транзитного движка  ← НОВОЕ
│       ├── test_auth.py
│       ├── test_payments.py
│       └── conftest.py
│
├── frontend/
│   └── src/
│       ├── components/
│       │   ├── NatalChart.jsx         # D3.js SVG-колесо — поддерживает двойное кольцо
│       │   │                          #   Props: planets, houses, aspects, ascendant,
│       │   │                          #   midheaven, timeUnknown
│       │   │                          #   (транзитное кольцо добавляется через
│       │   │                          #    transitPlanets prop — см. раздел интеграции)
│       │   ├── TransitTimeline.jsx    # Временная шкала транзитов  ← НОВОЕ
│       │   │                          #   Props: chartId, fromDate, toDate
│       │   │                          #   Режимы: список по дням + панель интерпретации
│       │   │                          #   Фильтры: планеты, аспекты, орб
│       │   │                          #   SSE: /transits/interpret, /transits/event/interpret
│       │   ├── Interpretation.jsx     # Стриминг AI-текста (SSE)
│       │   └── BirthForm.jsx          # Форма ввода данных рождения
│       ├── api/
│       │   └── client.js              # API-клиент + SSE-подключение
│       ├── pages/
│       │   ├── Home.jsx
│       │   ├── Chart.jsx              # Интегрирует NatalChart + TransitTimeline
│       │   ├── Login.jsx
│       │   ├── Register.jsx
│       │   ├── Profile.jsx
│       │   └── Pricing.jsx
│       ├── hooks/
│       │   └── useAuth.js
│       └── App.jsx
│
├── data/
│   └── ephe/                          # Файлы Swiss Ephemeris (.se1, ~80 МБ)
│
├── alembic/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│       ├── 001_baseline.py
│       └── 002_phase4_auth_payments.py
│
├── alembic.ini
├── docker-compose.yml
├── Dockerfile
├── Makefile
├── pyproject.toml
├── .env
└── .env.example
```

---

## Карта зависимостей — транзитный модуль

```
backend/transit/engine.py
    ├── импортирует из backend/ephemeris/calculator.py
    │       PLANETS, ZODIAC_SIGNS
    │       _datetime_to_jd()
    │       _longitude_to_sign()
    │       _calc_planet_position()   ← lru_cache, ключевая оптимизация
    │
    ├── импортирует из backend/ephemeris/aspects.py
    │       ASPECTS                   ← dict {"conjunction": 0.0, ...}
    │       _angular_distance()
    │
    └── возвращает List[TransitEvent] (dataclass)

backend/transit/prompts.py
    ├── импортирует из backend/interpretation/prompts.py
    │       _compact_profile()        ← сжимает natal для промпта
    │
    └── предоставляет
            build_transit_event_prompt()
            build_transit_period_prompt()
            get_template_transit_text()

backend/main.py
    ├── GET  /api/v1/chart/{id}/transits
    │       → transit.engine.calculate_transits()
    │       → transit_cache (TTL 7 дней)
    │
    ├── GET  /api/v1/chart/{id}/transits/interpret   (SSE)
    │       → transit.engine.calculate_transits()
    │       → transit.engine.get_transit_summary()
    │       → interpretation.router (GPT-4o → DeepSeek → шаблон)
    │
    └── POST /api/v1/chart/{id}/transits/event/interpret   (SSE)
            → transit.prompts.get_template_transit_text()
            → interpretation.router (GPT-4o → DeepSeek → шаблон)
```

---

## Схемы данных — транзиты (schemas.py)

| Схема | Поля | Где используется |
|---|---|---|
| `TransitRequest` | `from_date`, `to_date` | Query-параметры GET /transits |
| `TransitEvent` | `date`, `transit_planet`, `natal_planet`, `aspect_type`, `orb`, `exact_date` | Элемент ответа |
| `TransitResponse` | `chart_id`, `from_date`, `to_date`, `events: list[TransitEvent]` | Ответ GET /transits |

---

## API-эндпоинты транзитов

| Метод | Путь | Описание |
|---|---|---|
| GET | `/api/v1/chart/{id}/transits` | Список транзитов за период. Query: `from_date`, `to_date`, `planet?`, `max_orb?` |
| GET | `/api/v1/chart/{id}/transits/interpret` | SSE-стриминг обзора периода. Query: `from_date`, `to_date` |
| POST | `/api/v1/chart/{id}/transits/event/interpret` | SSE интерпретация одного события. Body: `{transit_planet, natal_planet, aspect_type}` |

---

## Что НЕ входит в текущую реализацию (запланировано позже)

- Двойное колесо в `NatalChart.jsx` (транзитное кольцо снаружи) — в `TransitTimeline.jsx` реализован только список.
- Redis-кэш — используется in-memory `transit_cache` из `backend/cache.py`.
- Celery-очередь для периодов > 30 дней — сейчас синхронный расчёт с лимитом 366 дней.
- Ретроградные станции — `applying` определяется по знаку скорости, точные даты станций не вычисляются.
