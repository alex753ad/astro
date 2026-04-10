# Astro SPA — Порядок запуска и работа приложения

## 1. Предварительные требования

| Инструмент | Версия | Зачем |
|---|---|---|
| Python | 3.11+ | Backend (FastAPI, pyswisseph) |
| Node.js | 18+ | Frontend (React, Vite) |
| Docker + Compose | любая актуальная | PostgreSQL в dev |
| Git | — | клонирование |

---

## 2. Первый запуск (с нуля)

### Шаг 1 — Клонировать и настроить переменные окружения

```bash
git clone <repo-url> astro-spa
cd astro-spa
cp .env.example .env
```

Минимально необходимые переменные в `.env` для запуска с транзитами:

```env
# Обязательно
DATABASE_URL=postgresql://astro:astro@localhost:5432/astro
JWT_SECRET=<сгенерируйте: python -c "import secrets; print(secrets.token_urlsafe(64))">
EPHE_PATH=./data/ephe

# AI (нужен хотя бы один для интерпретаций; без них работает шаблонный fallback)
OPENAI_API_KEY=sk-...
DEEPSEEK_API_KEY=sk-...

# Опционально (Фаза 4)
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=
STRIPE_PRICE_ID_PRO=
STRIPE_PRICE_ID_PREMIUM=
CORS_ORIGINS=["http://localhost:5173"]
DEBUG=true
```

### Шаг 2 — Скачать файлы эфемерид Swiss Ephemeris

Без них `pyswisseph` не считает позиции планет:

```bash
mkdir -p data/ephe
# Скачать базовый набор (~80 МБ, покрывает 1800–2400 гг.)
# Источник: https://www.astro.com/ftp/swisseph/ephe/
wget -P data/ephe https://www.astro.com/ftp/swisseph/ephe/seas_18.se1
wget -P data/ephe https://www.astro.com/ftp/swisseph/ephe/semo_18.se1
wget -P data/ephe https://www.astro.com/ftp/swisseph/ephe/sepl_18.se1
```

Если `wget` недоступен — скачать вручную и положить в `data/ephe/`.

### Шаг 3 — Запустить PostgreSQL

```bash
docker compose up -d db
# Проверить что поднялась:
docker compose ps
```

### Шаг 4 — Установить Python-зависимости

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"            # или: pip install -r requirements.txt
```

### Шаг 5 — Применить миграции

```bash
alembic upgrade head
```

### Шаг 6 — Запустить backend

```bash
uvicorn backend.main:app --reload --port 8000
```

Проверить: `http://localhost:8000/health` → `{"status": "ok", ...}`

### Шаг 7 — Запустить frontend

```bash
cd frontend
npm install
npm run dev
```

Открыть: `http://localhost:5173`

---

## 3. Ежедневный запуск (уже настроено)

```bash
# Терминал 1 — база данных
docker compose up -d db

# Терминал 2 — backend
source .venv/bin/activate
uvicorn backend.main:app --reload --port 8000

# Терминал 3 — frontend
cd frontend && npm run dev
```

Или через Makefile (если настроен):

```bash
make dev
```

---

## 4. Как работает приложение — сквозной поток

### 4.1 Расчёт натальной карты

```
Пользователь заполняет BirthForm.jsx
    → POST /api/v1/chart/calculate
        → geo.py: Nominatim геокодирует место → lat/lon/timezone
        → geo.py: resolve_utc_datetime() конвертирует локальное время в UTC
        → calculator.py: calculate_full_chart()
            → _calc_planet_position() для каждой планеты (lru_cache по JD)
            → calculate_houses() — Плацидус/Кох/Equal/Whole Sign
            → assign_houses() — привязка планет к домам
            → aspects.py: calculate_aspects() — все аспекты между планетами
        → Сохраняет NatalChart в PostgreSQL
    ← Возвращает NatalChartResponse (planets, houses, aspects, ascendant, MC)

Фронтенд рендерит NatalChart.jsx (D3.js SVG-колесо)
```

### 4.2 Расчёт транзитов

```
Пользователь выбирает период дат в TransitTimeline.jsx
    → GET /api/v1/chart/{id}/transits?from_date=…&to_date=…
        → Загружает NatalChart из БД (natal_planets — список позиций)
        → Проверяет transit_cache (TTL 7 дней)
        → transit/engine.py: calculate_transits()
            → Для каждого шага времени (4ч для быстрых планет, 24ч для медленных):
                → _calc_planet_position() — позиция транзитной планеты (lru_cache)
                → aspects.py: _angular_distance() к каждой натальной планете
                → Если орб ≤ TRANSIT_ORBS[aspect] — создать TransitEvent
                → Дедупликация по (транзит, натал, аспект, неделя)
                → _find_exact_aspect() — бисекция для точного времени (±5 мин)
        → Сохраняет в transit_cache
    ← Возвращает TransitResponse {chart_id, from_date, to_date, events[]}

TransitTimeline.jsx отображает события по дням с фильтрами
```

### 4.3 AI-интерпретация транзита (клик на событие)

```
Пользователь кликает на событие в TransitTimeline.jsx
    → POST /api/v1/chart/{id}/transits/event/interpret
        Body: {transit_planet, natal_planet, aspect_type}
        → interpretation/router.py: fallback-цепочка
            1. GPT-4o (если OPENAI_API_KEY задан)
            2. DeepSeek V3 (если DEEPSEEK_API_KEY задан)
            3. transit/prompts.py: get_template_transit_text() — шаблонный текст
        → SSE-стриминг текста чанками
    ← data: {"text": "…"} … data: [DONE]

InterpretationPanel в TransitTimeline.jsx рендерит текст по мере получения
```

### 4.4 Обзор периода

```
Пользователь нажимает "Интерпретировать период"
    → GET /api/v1/chart/{id}/transits/interpret?from_date=…&to_date=…
        → calculate_transits() — весь список событий
        → get_transit_summary() — топ-10 значимых + статистика
        → transit/prompts.py: build_transit_period_prompt()
            (фильтрует до 20 значимых транзитов для промпта)
        → interpretation/router.py → GPT-4o / DeepSeek / шаблон
        → SSE-стриминг
    ← Обзор периода в панели интерпретации
```

---

## 5. Ключевые оптимизации производительности

| Механизм | Где | Эффект |
|---|---|---|
| `lru_cache` на `_calc_planet_position(jd)` | `calculator.py` | Одна планета в одном JD считается один раз |
| Шаг 24ч для медленных планет | `engine.py`, `SLOW_STEP_HOURS` | В 6× меньше вычислений для Юпитер–Плутон |
| Шаг 4ч для быстрых планет | `engine.py`, `FAST_STEP_HOURS` | Достаточная точность для Луны и Солнца |
| `transit_cache` (TTL 7 дней) | `cache.py` + `main.py` | Повторный запрос того же периода — мгновенно |
| Дедупликация по неделе | `engine.py`, `seen` set | Один транзит не записывается дважды за период орба |

**Важно для Луны:** шаг 4ч достаточен для обнаружения аспектов, но `exact_date` уточняется бисекцией до ±5 минут. Если нужна точность до минуты — уменьшите `FAST_STEP_HOURS` до 1 в `engine.py`.

---

## 6. Проверка работы транзитного модуля

### Curl-запросы

```bash
# 1. Создать карту
curl -s -X POST http://localhost:8000/api/v1/chart/calculate \
  -H "Content-Type: application/json" \
  -d '{"birth_date": "1990-06-15", "birth_time": "14:30", "birth_place": "Moscow"}' \
  | python -m json.tool | grep '"id"'
# Скопировать chart_id из ответа

# 2. Получить транзиты за месяц
curl -s "http://localhost:8000/api/v1/chart/{chart_id}/transits?from_date=2026-04-01&to_date=2026-04-30" \
  | python -m json.tool

# 3. Интерпретация одного события
curl -s -X POST http://localhost:8000/api/v1/chart/{chart_id}/transits/event/interpret \
  -H "Content-Type: application/json" \
  -d '{"transit_planet": "Jupiter", "natal_planet": "Sun", "aspect_type": "conjunction"}'

# 4. SSE-обзор периода (следить за стримингом)
curl -N "http://localhost:8000/api/v1/chart/{chart_id}/transits/interpret?from_date=2026-04-01&to_date=2026-04-30"
```

### Swagger UI

Открыть `http://localhost:8000/docs` → раздел **transits**.

### Запуск тестов

```bash
pytest backend/tests/test_transits.py -v
pytest backend/tests/ -v --cov=backend/transit
```

---

## 7. Частые проблемы

| Симптом | Причина | Решение |
|---|---|---|
| `swe.Error` при расчёте | Нет файлов эфемерид | Проверить `data/ephe/`, скачать `.se1` файлы |
| `ModuleNotFoundError: backend.transit.prompts` | Не создан `transit/__init__.py` | `touch backend/transit/__init__.py` |
| `KeyError: _compact_profile` | `interpretation/prompts.py` не содержит `_compact_profile` | Добавить функцию или адаптировать импорт в `transit/prompts.py` |
| Транзитов 0 | Слишком маленький орб | Проверить `TRANSIT_ORBS` в `engine.py`, по умолчанию 1.5–2° |
| Кэш не сбрасывается | TTL 7 дней | Перезапустить backend (in-memory кэш) или изменить параметры запроса |
| SSE-стрим не приходит в браузер | Nginx буферизует ответ | Добавить заголовок `X-Accel-Buffering: no` (уже есть в `main.py`) |
