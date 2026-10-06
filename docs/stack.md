# Стек

Вынесено из корневого CLAUDE.md 06.10.2026. Правка меняет стек — этот файл правится в том же коммите.

| Слой | Технология |
|---|---|
| Frontend | React 18.3, React Router 6, Vite 5, Tailwind 3.4, D3.js |
| Backend | Python 3.12, FastAPI, Uvicorn |
| БД / ORM | PostgreSQL 18, SQLAlchemy 2.0, Alembic |
| Кэш / очереди | Redis 7, Celery |
| Астрология | pyswisseph (Swiss Ephemeris) |
| AI | интерпретации — DeepSeek Pro (→ GPT-4o → шаблон); прогнозы в приложении — DeepSeek Pro; общий астрокалендарь — без модели (с 04.10.2026). Подробно — [docs/forecasts.md](docs/forecasts.md) |
| Аутентификация | JWT, Google OAuth 2.0, bcrypt |
| Платежи | ЮKassa (в разработке) — Robokassa и Stripe удалены 19.08.2026 как мёртвый код |
| Email | Resend API |
| Геокодинг | Nominatim |
| Хостинг | Timeweb VPS: Nginx + Docker Compose (api, bot, postgres, redis, uptime-kuma) |
| CI/CD | GitHub Actions → SSH-деплой на VPS (ручной запуск джоба); фронтенд пересобирается тем же `05-update.sh`, отдельного запуска не требует |
| PDF | ReportLab |
