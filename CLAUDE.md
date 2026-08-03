# CLAUDE.md — Astrea Timeline

## Правила работы
1. Спрашивай вместо того чтобы угадывать
2. Пиши минимальный код
3. Делай только то о чём прошу
4. Фокусируйся на результате, а не инструкции
5. Работай аккуратно и внимательно
6. Код не пиши пока я не скажу, отвечай кратко

---

## Проект

**Astrea Timeline** — веб-приложение: натальные карты, транзиты, лунный календарь, AI-интерпретации. Домен: astreatime.ru.
**Версия архитектуры:** 4.0 | Август 2026

---

## Стек

| Слой | Технология |
|---|---|
| Frontend | React 18.3, React Router 6, Vite 5, Tailwind 3.4, D3.js |
| Backend | Python 3.12, FastAPI, Uvicorn |
| БД / ORM | PostgreSQL 18, SQLAlchemy 2.0, Alembic |
| Кэш / очереди | Redis 7, Celery |
| Астрология | pyswisseph (Swiss Ephemeris) |
| AI | OpenAI GPT-4o → DeepSeek V3 → шаблоны; прогнозы — Anthropic Claude Sonnet → GPT-4o |
| Аутентификация | JWT, Google OAuth 2.0, bcrypt |
| Платежи | Robokassa (основной, RU), Stripe (legacy) |
| Email | Resend API |
| Геокодинг | Nominatim |
| Хостинг | Timeweb VPS: Nginx + Docker Compose (api, bot, postgres, redis, uptime-kuma) |
| CI/CD | GitHub Actions → SSH-деплой на VPS (backend), фронтенд — вручную скриптом |
| PDF | ReportLab |

**UI-инструменты (активные):**
- 21st.dev — готовые React-компоненты
- Framer Motion — анимации
- Ponytail — Tailwind-компоненты (CLI)

---

## Структура frontend

```
frontend/src/
├── App.jsx
├── main.jsx
├── index.css
├── pages/
│   ├── LandingPage.jsx
│   ├── HomePage.jsx
│   ├── ChartPage.jsx
│   ├── ProfilePage.jsx
│   ├── CRMPage.jsx
│   ├── AdminPage.jsx
│   ├── PlannerPage.jsx
│   ├── LunarCalendarPage.jsx
│   ├── SolarReturnPage.jsx    # in progress
│   ├── SynastryPage.jsx       # in progress
│   ├── RelocationPage.jsx     # in progress
│   ├── PortalPage.jsx         # клиентский портал
│   ├── IntakePage.jsx         # анкета клиента
│   ├── OrionPage.jsx          # тарифы
│   ├── ZodiacPage.jsx
│   ├── SharePage.jsx
│   └── GiftPage.jsx
├── components/
│   ├── NatalChart.jsx      # SVG колесо натальной карты (D3)
│   ├── TransitTimeline.jsx # временная шкала транзитов
│   ├── AuthModal.jsx
│   ├── RagChat.jsx         # чат Астреи (RAG)
│   ├── Toast.jsx
│   └── ThemeToggle.jsx
└── hooks/
    └── useAuth.jsx
```

---

## Структура backend

```
backend/
├── main.py
├── models.py
├── schemas.py
├── config.py
├── database.py
├── cache.py
├── celery_app.py
├── tasks.py
├── limiter.py
├── authz.py
├── metrics.py
├── email_service.py
├── natal_pdf.py
├── health.py
├── auth/
├── calendar/
├── crm/
├── ephemeris/
├── interpretation/
├── transit/
├── payments/          # robokassa_service.py (основной), stripe_service.py (legacy)
├── admin/
├── push/              # web push (pywebpush + VAPID)
├── notifications/     # telegram
├── pilot/             # пилотная Telegram-программа
├── feedback/
├── exit_survey/
└── profile/
```

---

## Тарифы

| | Free | Lite | Pro | Premium |
|---|---|---|---|---|
| Цена (мес/год) | 0 | 790₽ / 7490₽ | 1990₽ / 19900₽ | 7990₽ / 79900₽ |
| Карты | 4/мес | 4/мес | ∞ | ∞ |
| AI-интерпретации | 1 бесплатная навсегда, дальше шаблон | 5/мес | 15/мес (GPT-4o) | 100/мес (GPT-4o) |
| AI-транзиты | 2 (значимые) | 3/мес | полные + AI | полные + AI |
| Планер | — | — | ✓ | ✓ |
| CRM / PDF-брендинг / авторские тексты | — | — | — | ✓ |

Лимиты применяются через `TierLimiter` (`auth/rate_limits.py`), расход считается в `UsageCounter`.

---

## Ключевые API эндпоинты

```
POST /api/v1/chart/calculate
GET  /api/v1/chart/{id}/interpret       # SSE
GET  /api/v1/chart/{id}/transits/interpret  # SSE
GET  /api/v1/chart/{id}/forecast/daily|weekly|monthly
POST /api/v1/auth/register
POST /api/v1/auth/login
GET  /api/v1/auth/google
POST /api/v1/payments/checkout
POST /api/v1/payments/webhook
POST /api/v1/clients                    # CRM (Premium)
```

---

## AI Fallback Chain

```
GPT-4o → DeepSeek V3 → Template engine
```

---

## Деплой

Всё на одном сервере: **Timeweb VPS**.

```
push → main
  ├── GitHub Actions: pytest (backend) + vite build (frontend)
  └── deploy job (SSH на VPS) → ./05-update.sh
        git pull → dump БД → docker compose up -d --no-deps api bot
        → alembic upgrade head → /health check → rollback при ошибке
        → фронтенд пересобирается тем же скриптом, если менялся frontend/
```

- **Backend**: Docker Compose (`api`, `bot`, `postgres`, `redis`, `uptime-kuma`), Nginx проксирует `/api/` и `/health` на `127.0.0.1:8000`. Один образ, `SERVICE_ROLE=bot` переключает контейнер на Telegram-бота.
- **Frontend**: деплой автоматический через CI (`04-frontend-deploy.sh`: npm run build → копирование `dist/` → reload nginx), запускается из `05-update.sh` только если менялся `frontend/`. Ручной запуск `./04-frontend-deploy.sh` на сервере остаётся доступен.
- **Бэкапы**: systemd-таймер, `pg_dump` ежедневно в 03:30, ротация 14 дней.

---

## Важные соглашения

- Не использовать `sudo` с npm
- Framer Motion — только поверх готовых компонентов
- Новые компоненты брать из 21st.dev или Ponytail, не генерировать с нуля
- Один компонент за раз, не рефакторить всё сразу
- Перед правкой файла — уточнить задачу
