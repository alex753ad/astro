# ARCHITECTURE_v2 — Canonical Architecture (v2.3)

Документ описывает текущую архитектуру системы. Источник истины — код в репозитории.

Версия: 2.3 | 09 июля 2026 | Sprint v3.1

## 1. Назначение

Astrea Timeline — веб-приложение для построения натальных карт, расчёта транзитов, лунного календаря и генерации персональных астрологических интерпретаций с помощью LLM.

Монетизация — подписочная модель 4 тарифов: Free / Lite (790₽) / Pro (1990₽) / Premium (7990₽) через Stripe. Trial отсутствует.

---

Примечание: этот файл — canonical-версия архитектуры. Удалил альтернативные версии (`архитектура.md`) чтобы избежать рассинхронизации.

## 2. Снимок репозитория (root) — текущее состояние (2026-07-09)

Корень репозитория содержит (ключевые элементы):

- .dockerignore, .gitignore, .env.example, .vscode/
- .github/
- ARCHITECTURE_v2.md (этот файл)
- App.jsx, PlannerPage.jsx, TransitTimeline.jsx, client.js
- backend/ (директория)
- frontend/ (директория)
- docker-compose.yml, Dockerfile, railway.toml, vercel.json
- alembic/, alembic.ini
- основные утилиты и модули: main.py, engine.py, house_passages.py, generate_pdf.py, natal_pdf.py
- большие артефакты/данные: log.json, natal_chart.pdf
- вспомогательные текстовые файлы: замечания.txt, образец.txt и пр.

---

## 3. Архитектура верхнего уровня

Frontend (Vercel)
    ↓
Backend (Railway, FastAPI)
    ↓
PostgreSQL + Redis
    ↓
OpenAI / DeepSeek (LLM, fallback-цепочка)
    ↓
Stripe (платежи, прайсы + Coupon API)
    ↓
Resend (транзакционные письма)
    ↓
Google OAuth
    ↓
Nominatim (геокодинг)
    ↓
Swiss Ephemeris (.se1 файлы)

---

## 4. Технологический стек (актуально)

Backend
- Python 3.12 (Docker: python:3.12-slim)
- FastAPI, SQLAlchemy 2.0, Alembic
- PostgreSQL 16, Redis
- pyswisseph, pydantic 2.x
- Celery (background tasks), httpx
- slowapi (rate limiting)
- geopy, timezonefinder, pytz

Frontend
- React (встраиваемая версия в корне repo), Vite, Tailwind
- dist/ собранный фронтенд хранится в frontend/dist

Инфраструктура
- Railway (backend + workers), Vercel (frontend), GitHub Actions CI
- Docker Compose для локального окружения
- Resend — транзакционные письма

---

## 5. Backend: синхронизированная структура (по фактическим файлам)

Найденные модули и ключевые файлы в backend/: 

- backend/__init__.py
- backend/main.py — FastAPI приложение (точка входа для backend)
- backend/config.py — настройки и чтение env
- backend/database.py — SQLAlchemy engine / сессии
- backend/models.py — ORM модели
- backend/schemas.py — Pydantic схемы
- backend/cache.py — обёртка Redis TTL-кэша
- backend/limiter.py — rate-limiting helpers (slowapi integration)
- backend/celery_app.py — инициализация Celery
- backend/tasks.py — Celery задачи (retention emails, pdf generation, background transits)
- backend/email_service.py — Resend интеграция, шаблоны писем
- backend/natal_pdf.py — PDF генерация для карт
- backend/health.py — /health endpoints
- backend/share_router.py — маршруты шаринга карт (public tokens)
- backend/onboarding_router.py — internal endpoints для онбординга (Railway Cron)

Директории:
- backend/ephemeris/ — содержит вычисления ephemeris (calculator, aspects, houses, geo)
- backend/interpretation/ — LLM integration, fallback-цепочка, prompts
- backend/transit/ — логика транзитов и house_passages
- backend/calendar/ — lunar engine
- backend/auth/ — Google OAuth, jwt, passwords, dependencies, rate limit logic
- backend/payments/ — Stripe интеграция, webhooks
- backend/profile/ — profile routes, charts CRUD
- backend/tests/ — тесты, фикстуры
- backend/crm/, backend/admin/ — вспомогательные модули (доступные директории)

Замечания:
- Некоторые модули (например `natal_pdf.py`) представлены как отдельные файлы в корне backend/ вместо вложенных подпапок, что отражено в структуре.
- `house_passages.py` доступен и в корне репозитория; в архитектуре он помечен как часть transit/ — рекомендую при следующий рефакторинге переместить в backend/transit/ для консистентности.

---

## 6. Frontend: синхронизированная структура (по фактическим файлам)

Ключевые элементы в frontend/:
- frontend/package.json, package-lock.json
- frontend/src/ — исходники (в репозитории пустая директория src/ — основной фронтенд в корневых JSX-файлах)
- frontend/index.html, frontend/server.js, frontend/vite.config.js, frontend/tailwind.config.js
- frontend/PlannerPage.jsx, frontend/TransitTimeline.jsx, frontend/TransitsPage.jsx, frontend/LoginPage.jsx, frontend/RegisterPage.jsx, frontend/PaymentSuccessPage.jsx
- frontend/dist/ — собранный артефакт
- frontend/public/ — публичные ассеты

Маршруты и страницы (соответствуют компонентам в корне frontend/):
- / — Home (реализован частично в App.jsx в корне repo)
- /planner — PlannerPage.jsx
- /transits — TransitsPage.jsx

Замечания:
- Frontend частично размещён в корне репозитория (App.jsx в корне), а также в папке frontend/. Это может путать; рекомендую консолидировать фронтенд-исходники в frontend/src/ и удалить лишние дубли в корне.

---

## 7. API Endpoints (актуальные)

(Синхронизированы с backend/routers и файлами)

Chart
- POST /api/v1/chart/calculate
- POST /api/v1/chart/save-anonymous
- GET /api/v1/chart/{id}
- GET|POST /api/v1/chart/{id}/interpret

Transits & Forecast
- GET /api/v1/chart/{id}/transits
- GET /api/v1/chart/{id}/transits/interpret
- POST /api/v1/chart/{id}/transits/event/interpret
- GET /api/v1/chart/{id}/transits/async
- GET /api/v1/chart/{id}/forecast/daily|weekly|monthly
- GET /api/v1/chart/{id}/planner/monthly

Auth
- POST /api/v1/auth/register, login, refresh, google
- GET /api/v1/auth/me
- DELETE /api/v1/auth/me

Payments
- POST /api/v1/payments/checkout
- POST /api/v1/payments/portal
- POST /api/v1/payments/webhook

Profile
- GET /api/v1/profile/charts
- DELETE /api/v1/profile/charts/{id}
- GET /api/v1/profile/history
- GET /api/v1/profile/subscription
- DELETE /api/v1/profile/data

Internal
- POST /api/v1/internal/onboarding-emails
- POST /api/v1/internal/weekly-digest
- POST /api/v1/internal/coupon/generate

Health
- GET /health, /health/db, /health/ai

---

## 8. Тарифы и биллинг (обновлённая формулировка)

Тарифы:
- Free: 0 ₽/мес — базовый доступ, 1 карта/день, ограниченный доступ к транзитам
- Lite: 790 ₽/мес — 5 карт/мес, 3 AI-интерпретации, лунный календарь 12 мес
- Pro: 1 990 ₽/мес — неограниченные карты, 15 AI-интерпретаций, транзиты и RAG-чат, 5 PDF/мес
- Premium: 7 990 ₽/мес — всё Pro + 100 AI-интерпретаций, CRM-интеграция, 50 PDF/мес

Контроль: ограничения реализуются на уровне бекенда (TierRateLimiter + slowapi) и в бэкенд-логике (require_tier).

---

## 9. Email и домен (обновлённые контактные данные)

- Продакшен домен фронтенда: https://astro-navy-one.vercel.app (homepage в настройках репозитория)
- Транзакционные письма: Resend, FROM: noreply@astreatime.ru (SPF/DKIM/DMARC должны быть настроены для домена astreatime.ru)

---

## 10. Рекомендации и следующие шаги

1. Консолидация фронтенда: переместить все JSX-исходники в frontend/src/ и удалить/архивировать дубликаты в корне (App.jsx и т.п.).
2. Перенести `house_passages.py` в backend/transit/ и удалить дубликаты из корня.
3. Оставить этот файл как canonical (`ARCHITECTURE_v2.md`) и удалить/архивировать любые другие версии (выполнено).
4. При следующем релизе: обновлять только ARCHITECTURE_v2.md.

---

Коммит: "Normalize architecture: canonical ARCHITECTURE_v2.md (v2.3), sync with codebase, remove duplicates"
