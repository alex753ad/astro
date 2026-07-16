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

**Astrea Timeline** — веб-приложение: натальные карты, транзиты, лунный календарь, AI-интерпретации.
**Версия архитектуры:** 3.1 | Июль 2026

---

## Стек

| Слой | Технология |
|---|---|
| Frontend | React 18.3, React Router 6, Vite 5, Tailwind 3.4 |
| Backend | Python 3.12, FastAPI, Uvicorn |
| БД / ORM | PostgreSQL 16, SQLAlchemy 2.0, Alembic |
| Кэш / очереди | Redis 7, Celery |
| Астрология | pyswisseph (Swiss Ephemeris) |
| AI | OpenAI GPT-4o → DeepSeek V3 → шаблоны |
| Аутентификация | JWT, Google OAuth 2.0, bcrypt |
| Платежи | Stripe |
| Email | Resend API |
| Геокодинг | Nominatim |
| Deploy | Railway (backend + worker + cron), Vercel (frontend) |
| CI/CD | GitHub Actions |
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
│   ├── PlannerPage.jsx
│   ├── LunarCalendarPage.jsx
│   ├── ZodiacPage.jsx
│   ├── SharePage.jsx
│   └── GiftPage.jsx
├── components/
│   ├── NatalChart.jsx     # SVG колесо натальной карты
│   ├── AuthModal.jsx
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
├── tasks.py
├── auth/
├── calendar/
├── crm/
├── ephemeris/
├── interpretation/
├── payments/
├── profile/
└── transit/
```

---

## Тарифы

| | Free | Lite | Pro | Premium |
|---|---|---|---|---|
| Цена | 0 | 790₽/мес | 1990₽/мес | 7990₽/мес |
| Карты/день | 1 | 5 | ∞ | ∞ |
| AI-интерпретации | — | 3 | 15 | 100 |
| PDF-отчёты | — | — | 5 | ∞ |
| RAG-чат | — | — | ✓ | ✓ |
| CRM | — | — | — | ✓ |

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

```
push → main
  ├── GitHub Actions (pytest)
  ├── Railway → FastAPI + Celery + Cron
  └── Vercel → Frontend
```

---

## Важные соглашения

- Не использовать `sudo` с npm
- Framer Motion — только поверх готовых компонентов
- Новые компоненты брать из 21st.dev или Ponytail, не генерировать с нуля
- Один компонент за раз, не рефакторить всё сразу
- Перед правкой файла — уточнить задачу
