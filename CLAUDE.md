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
| Платежи | ЮKassa (в разработке) — Robokassa и Stripe удалены 19.08.2026 как мёртвый код |
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
├── payments/          # common.py (провайдер-независимая логика) + payments_router.py;
│                      # роутер ЮKassa появится здесь отдельной задачей
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
GET  /api/v1/payments/subscription       # текущая подписка
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
        git pull → dump БД → docker compose up -d --no-deps api bot worker beat
        → alembic upgrade head → /health check → rollback при ошибке
        → фронтенд пересобирается тем же скриптом, если менялся frontend/
```

✅ **Больше не критично: `05-update.sh`, `docker-compose.yml` и
`07-backup-cron.sh` синхронизируются сами.** Раньше `git pull` на сервере
обновлял только каталог `app/`, а копии этих трёх файлов рядом с ним —
`/opt/astro/05-update.sh`, `/opt/astro/docker-compose.yml`,
`/opt/astro/07-backup-cron.sh` — не подтягивались автоматически. С
14.08.2026 `05-update.sh` сам копирует все три файла из
`app/deploy/opt-astro/` поверх рабочих копий сразу после `git pull` — при
каждом обычном запуске и при `--backend-only` (не при `--frontend-only`,
там `git pull` для `app/` не выполняется). Ручной шаг больше не нужен.
(nginx-конфиги — отдельный случай, их копирует сам `04-frontend-deploy.sh`
при каждом запуске, это не менялось).

Пропущенный вручную шаг уже дважды ронял прод из-за этого рассинхрона:
09.08.2026 — новые прод-guard'ы уже действовали в приложении, а
preflight-проверки и логика отката в `05-update.sh` на сервере ещё были
старыми; 14.08.2026 — фикс в `07-backup-cron.sh` был закоммичен, но
ночной бэкап продолжал падать, потому что таймер дёргал старую копию
скрипта рядом с `app/`. Второй случай и стал поводом сделать
синхронизацию автоматической.

- **Backend**: Docker Compose (`api`, `bot`, `worker`, `beat`, `postgres`, `redis`, `uptime-kuma`), Nginx проксирует `/api/` и `/health` на `127.0.0.1:8000`. Один образ, `SERVICE_ROLE` переключает роль контейнера (`bot` — Telegram-бот, `worker`/`beat` — Celery).
- **Frontend**: деплой автоматический через CI (`04-frontend-deploy.sh`: npm run build → копирование `dist/` → reload nginx), запускается из `05-update.sh` только если менялся `frontend/`. Ручной запуск `./04-frontend-deploy.sh` на сервере остаётся доступен.
- **Бэкапы**: systemd-таймер, `pg_dump` ежедневно в 03:30 (шифруется `age`, выгружается за пределы хоста), ротация 14 дней локально.

---

## Деплой — обязательная процедура

### Разделение ответственности

Claude Code **не имеет SSH-доступа к серверу**. Всё, что делается на VPS,
выполняет владелец руками. Поэтому Claude Code обязан:

- никогда не предлагать редактировать файлы напрямую на сервере;
- любую правку вносить только в репозиторий и доставлять через `git push`;
- если нужно действие на сервере — выдать **готовый блок команд одним куском**,
  без пояснений между строками, чтобы владелец вставил их одной вставкой;
- в командах не использовать `sed` с текстом, содержащим `|`, `&`, кавычки или
  кириллицу — только `python3 - <<'PYEOF'` с точным поиском строки и проверкой
  `assert count == 1`.

### Железное правило: сервер не редактируем

Каталог `/opt/astro/app` — это рабочая копия git. Любая ручная правка в нём
блокирует следующий `git pull` и роняет деплой. Уже случалось дважды.
Если правка нужна срочно — сделать её на сервере, **сразу** продублировать в
репозиторий и при первом же деплое откатить локальную версию через
`git checkout --`.

### Файлы, которые портятся сами

`npm run build` (он же `04-frontend-deploy.sh`) на каждом запуске
перезаписывает файлы, которые лежат в репозитории. Из-за этого `git status` на
сервере никогда не бывает чистым, и `git pull` падает:

| Файл | Кто портит |
|---|---|
| `frontend/dist/index.html` | `vite build` |
| `frontend/dist/_redirects` | `vite build` |
| `frontend/public/sitemap.xml` | `generate-sitemap.js` (запускается из `build`) |

`frontend/dist/` уже в `.gitignore` (строка 51), но два файла были закоммичены
раньше правила и продолжают отслеживаться. Лечится один раз:

```bash
git rm --cached frontend/dist/index.html frontend/dist/_redirects
echo 'frontend/public/sitemap.xml' >> .gitignore
git rm --cached frontend/public/sitemap.xml
git commit -m "chore: не отслеживать генерируемые при сборке файлы"
```

До тех пор перед каждым деплоем на сервере нужно:

```bash
cd /opt/astro/app && git checkout -- . && git status --short
```

### Порядок деплоя

1. **Claude Code**: прогнать `pytest` и `vite build` локально. Если тесты
   падают — не пушить молча. Объяснить, воспроизводятся ли падения на коде
   *до* правок, и дождаться решения владельца.
2. **Claude Code**: `git push` в `main`. Автодеплой запускается сам.
3. **Claude Code**: следить за GitHub Actions до конца, не отчитываться
   «запушено» раньше, чем отработает job `deploy`.
4. **Владелец**: если деплой упал на `git pull` — выполнить блок из пункта
   «Файлы, которые портятся сами», затем сказать Claude Code перезапустить:
   `gh run rerun <ID> --failed`.
5. **Владелец**: проверить результат по чек-листу приёмки.

`05-update.sh`, `docker-compose.yml` и `07-backup-cron.sh` больше не нужно
копировать руками — `05-update.sh` сам синхронизирует все три файла из
`app/deploy/opt-astro/` поверх рабочих копий в `/opt/astro` сразу после
`git pull`, при каждом запуске (обычном и `--backend-only`). Исключение:
`--frontend-only` не делает `git pull` для `app/`, поэтому и синхронизацию
не запускает. Добавлено 14.08.2026 после падения ночного бэкапа — фикс в
`07-backup-cron.sh` был закоммичен, но не доезжал до сервера этим же путём,
что раньше случалось с `05-update.sh` и `docker-compose.yml`.

### Доступ сервера к GitHub

Пароли для git отключены с 2021 года. Сервер тянет код по SSH через deploy key
`~/.ssh/astro_deploy_key`, публичная часть добавлена в
Settings → Deploy keys репозитория (только чтение). Настроено 13.08.2026 после
падения деплоя с `Authentication failed`.

Если снова появится запрос логина — ключ или конфиг `~/.ssh/config` потерян,
проверять: `cd /opt/astro/app && git remote -v` должен показывать
`git@github.com:...`, а не `https://`.

### Бэкапы: что уже проверено, что нет

Прогон на проде 13.08.2026 прошёл полностью — дамп создаётся, шифруется,
расшифровывается ключом и читается как валидный архив.

- `age` ставится через `apt-get install -y age`, на чистом сервере его нет.
- Приватный ключ `/opt/astro/backups/astro-backup.key` **обязан** храниться
  вне сервера. Без него бэкапы бесполезны.
- `pg_restore -l` не читает дамп формата `-Fc` из потока — нужен файл с
  возможностью перемотки. Проверка внутри контейнера пишет во временный файл.
  Не «чинить» обратно на pipe.
- `BACKUP_S3_TARGET` не задан — копии только на этом сервере. Открытый риск:
  отказ диска уносит базу и бэкапы разом.

### Прод-гварды платежей — временно сняты

19.08.2026 из `backend/main.py` и `deploy/opt-astro/05-update.sh` убраны
проверки `ROBOKASSA_IS_TEST`/`ROBOKASSA_MERCHANT_LOGIN` (падали старт/деплой,
если в проде включён тестовый режим Robokassa — иначе подписки выдавались бы
без реальной оплаты). Причина снятия — сам Robokassa (вместе со Stripe) удалён как мёртвый
код (аккаунта и ключей никогда не было, ни одного платежа не проходило).

**Когда будет подключаться ЮKassa — обязательно вернуть аналогичные гварды**
под её переменными (эквивалент «тестовый режим» + «мерчант не настроен»), и
в `backend/main.py`, и в `deploy/opt-astro/05-update.sh` — именно отсутствие
второй проверки (в деплой-скрипте) уже дважды роняло прод из-за рассинхрона
(см. раздел «Деплой» выше), не полагаться только на проверку в приложении.

---

## Важные соглашения

- Не использовать `sudo` с npm
- Framer Motion — только поверх готовых компонентов
- Новые компоненты брать из 21st.dev или Ponytail, не генерировать с нуля
- Один компонент за раз, не рефакторить всё сразу
- Перед правкой файла — уточнить задачу
- Никогда не редактировать файлы напрямую на сервере — только через репозиторий
- «Готово» означает проверено в работе. Если проверить нельзя (нет браузера,
  Docker, доступа к серверу) — писать «код готов, приёмка не пройдена» и явно
  перечислять, что осталось непроверенным
