# Astro production stack — /opt/astro

## КРИТИЧНО: порядок первого запуска

`backend/main.py` при старте вызывает `Base.metadata.create_all(bind=engine)` —
это dev-заглушка на основе метаданных SQLAlchemy, не Alembic. Если `api` первым
тронет **пустую** Postgres, он создаст таблицы напрямую из текущих ORM-моделей,
в обход всей истории миграций: `alembic_version` останется пустой, а `alembic
upgrade head` после этого либо упадёт (таблицы уже есть), либо просто не будет
знать, какие миграции реально применены — схема разъедется с историей.

Обязательный порядок первого деплоя:

1. `./03-db-restore.sh '<railway-connection-string>'` — поднимает postgres и
   redis, снимает дамп с Railway, восстанавливает его в чистую локальную БД.
   Дамп уже содержит `alembic_version = 040_feedback_user_agent` — схема и
   история миграций приходят вместе, согласованно.
2. Только после подтверждённого восстановления — `docker compose up -d
   api bot`.

**Ни в коем случае не `docker compose up -d` всё сразу на пустой БД** — `api`
не должен быть первым процессом, который касается свежего Postgres.

## Makefile

- `make logs` — общие логи всех сервисов
- `make migrate` — `alembic upgrade head` внутри контейнера `api`
- `make shell-db` — psql внутрь `postgres`
- `make restart-api` — рестарт только `api`
- `make backup` — `pg_dump` в `backups/astro_<дата>_<время>.sql`

## Фронтенд (nginx на хосте, не в контейнере)

`nginx/astreatime.conf` — отдаёт `frontend/dist/` на `/`, проксирует `/api/`
и `/health` на `127.0.0.1:8000`. Один домен (`www.astreatime.ru`) для фронта
и бэка — same-origin, CORS не нужен. Пока только порт 80, HTTPS добавит
certbot отдельным шагом.

`./04-frontend-deploy.sh` — ставит Node.js LTS (если ещё не стоит), делает
`git pull` в `app/`, собирает `app/frontend`, публикует результат в
`frontend/dist/`, накатывает `nginx/astreatime.conf` и перечитывает nginx.

Для `VITE_GOOGLE_CLIENT_ID` (нужен только на этапе сборки фронта, в бэкендовом
`.env` ему не место — это отдельный build-time секрет, не рантайм-переменная
API): скопировать `frontend.env.example` в `frontend.env` (рядом с
`docker-compose.yml`, вне `app/`, чтобы `git pull` его не задевал) и вписать
значение. `04-frontend-deploy.sh` подхватывает его перед `npm run build`, если
файла нет — соберёт без него с предупреждением (фронт работает, просто вход
через Google Calendar не будет).

## Повседневное обновление

`./05-update.sh` — однокомандный деплой изменений из git. По умолчанию:
`git pull` → дамп БД в `backups/pre-update_<дата>_<время>.dump` → сборка
образа → пересоздание `api`/`bot`; если в пришедших коммитах менялся
`app/frontend/` — следом ещё и `04-frontend-deploy.sh`. Флаги `--backend-only`
/ `--frontend-only` ограничивают набор действий. Если сборка образа падает —
работавшие контейнеры не трогаются (сначала `docker compose build`, и только
при успехе — `up -d`). При 429 от Docker Hub во время сборки — 3 попытки с
паузой.

## Диагностика

`./06-diag.sh` — снимок состояния стека в `backups/diag_<дата>_<время>.txt`
(и на экран): статусы контейнеров, последние 100 строк логов каждого сервиса,
диск/память/swap, `nginx -t`, срок действия TLS-сертификата (если уже
выпущен), `curl` на `/health` и `/health/db`. Значения переменных из `.env`
нигде не печатаются, только имена.

## Файлы

- `docker-compose.yml` — прод-стек: postgres, redis, api, bot
- `.env.example` — скопировать в `.env`, заполнить реальными значениями
- `frontend.env.example` — скопировать в `frontend.env`, build-time секреты фронта
- `app/` — сюда клонируется репозиторий (build context для api/bot, источник для сборки фронта)
- `frontend/` — сюда кладётся собранный `dist/` для nginx на хосте
- `nginx/astreatime.conf` — конфиг сайта для nginx на хосте
- `backups/` — дампы БД и диагностические отчёты
- `03-db-restore.sh` — перенос БД с Railway
- `04-frontend-deploy.sh` — сборка и публикация фронтенда + nginx
- `05-update.sh` — повседневное обновление одной командой
- `06-diag.sh` — диагностический снимок состояния
