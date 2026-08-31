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
   api bot worker beat`.

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

⚠️ **Ни `04-frontend-deploy.sh`, ни `05-update.sh` нельзя запускать под
`sudo`.** Оба рассчитаны на пользователя `deploy` и берут `sudo` точечно.
Запуск целиком под `sudo` делает root-овыми `app/.git` и
`app/frontend/node_modules`, после чего обычный запуск падает. `nginx-backup`
и `frontend/dist` от этого защищены иначе — они создаются и наполняются
только через `sudo`, одним владельцем: root перезапишет любого, а `deploy`
root-овый каталог удалить не может.

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
образа → пересоздание `api`/`bot`/`worker`/`beat`; если менялись
`app/frontend/` или `app/deploy/opt-astro/nginx/` — следом ещё и
`04-frontend-deploy.sh` (он единственный, кто кладёт на сервер и `dist`, и
конфиг nginx). «Менялись» считается не по одному `git pull`, а диффом от
метки `.frontend-deployed-rev` — коммита последнего успешного деплоя
фронтенда; метка пишется только после того, как `04-frontend-deploy.sh`
вернул 0, поэтому упавший деплой не теряет изменения. Флаги `--backend-only`
/ `--frontend-only` ограничивают набор действий. Если сборка образа падает —
работавшие контейнеры не трогаются (сначала `docker compose build`, и только
при успехе — `up -d`). При 429 от Docker Hub во время сборки — 3 попытки с
паузой.

## Фоновые задачи (Celery) и служебные таймеры

`worker` и `beat` — тот же образ `astro-app`, роль переключается
`SERVICE_ROLE=worker`/`SERVICE_ROLE=beat` (см. `start.sh`). Раньше этих
процессов не было вовсе: `backend/tasks.py` и `backend/celery_app.py` были
написаны полностью, но каждый `.delay()`/`.apply_async()` клал задачу в Redis,
откуда её никто не забирал — рассылка клиентам из CRM отвечала успехом и
ничего не отправляла, `POST /transits/async` всегда истекал по таймауту.

`beat` сам по расписанию (`celery_app.py: beat_schedule`) ставит в очередь:
лунные возвращения, еженедельный дайджест, ежемесячную рассылку клиентам —
`worker` их забирает и выполняет. Держать `beat` только в одном экземпляре
обязательно: два `beat` поставят каждую периодическую задачу в очередь дважды.

Две служебные ручки — `POST /api/v1/internal/onboarding-emails` (письма
удержания дня 2/7) и `POST /api/v1/internal/pilot-tick` (жизненный цикл
пилотной программы) — не Celery-задачи, а обычный HTTP за
`X-Internal-Secret`, и Beat их не покрывает. Их дёргают systemd-таймеры
`astro-onboarding-emails.timer` / `astro-pilot-tick.timer` (ставит
`08-setup-automation.sh`), ежедневно в 06:15 и 06:20 UTC — после задач Beat
(06:00–06:10 UTC), чтобы не толкаться за одну БД в одну минуту.

## Диагностика

`./06-diag.sh` — снимок состояния стека в `backups/diag_<дата>_<время>.txt`
(и на экран): статусы контейнеров, последние 100 строк логов каждого сервиса,
диск/память/swap, `nginx -t`, срок действия TLS-сертификата (если уже
выпущен), `curl` на `/health` и `/health/db`. Значения переменных из `.env`
нигде не печатаются, только имена.

## CI/CD (GitHub Actions -> VPS по SSH)

Пуш в `main` → тесты (backend + frontend) → если оба джоба зелёные, джоб
`deploy` подключается по SSH и на самом сервере выполняет
`./05-update.sh --backend-only`: дамп БД → сборка образа → пересоздание
`api`/`bot`/`worker`/`beat` → `alembic upgrade head` → ожидание healthy → проверка
`/health` и `/health/db`. Если что-то из этого не прошло — скрипт сам
откатывает `api`/`bot`/`worker`/`beat` на предыдущий образ и завершается с ошибкой, джоб
`deploy` красный. Откатывается только образ контейнера, не применённые
миграции (down-миграции на проде с живыми данными — ручной шаг, не
автоматика).

Публикация фронтенда в CI не участвует — как и раньше, вручную через
`./04-frontend-deploy.sh`.

**Секреты репозитория** (Settings → Secrets and variables → Actions →
New repository secret):

| Секрет | Значение |
|---|---|
| `SSH_HOST` | `72.56.234.138` (или домен сервера) |
| `SSH_USER` | `deploy` |
| `SSH_PRIVATE_KEY` | приватный ключ пользователя `deploy` (тот, что использовался при SSH-hardening), содержимое файла целиком, включая `-----BEGIN...-----`/`-----END...-----` |

Ключ должен быть уже добавлен в `~deploy/.ssh/authorized_keys` на сервере —
это делалось при hardening'е, отдельно заводить ничего не нужно.

## Sentry (опционально)

Без `SENTRY_DSN`/`VITE_SENTRY_DSN` ничего не включается, поведение как
раньше. Чтобы включить:

1. На sentry.io создать организацию (если ещё нет) → New Project → платформа
   Python/FastAPI для бэкенда и отдельно (или тот же проект) React для
   фронтенда.
2. Скопировать DSN проекта (Settings проекта → Client Keys (DSN)).
3. Backend: вписать в `.env` → `SENTRY_DSN=...`, пересобрать (`./05-update.sh
   --backend-only`).
4. Frontend: вписать в `frontend.env` → `VITE_SENTRY_DSN=...`, пересобрать
   (`./04-frontend-deploy.sh`).

`send_default_pii=False`, `traces_sample_rate=0.1`, `environment=production`
на обеих сторонах. На бэкенде тело запроса перед отправкой в Sentry
дополнительно чистится от полей с `password`/`token`/`secret`/`key`/
`authorization` в названии — тем же фильтром, что и в логах 422-ошибок.

## Мониторинг (Uptime Kuma)

`./08-setup-automation.sh` поднимает `uptime-kuma` (только на
`127.0.0.1:3001`, лимит памяти 256 МБ) и настраивает доступ к нему на
`status.astreatime.ru` за basic-auth (nginx). Официально Uptime Kuma не
поддерживает работу из-под подпути на основном домене (ломаются ассеты и
WebSocket), поэтому — отдельный поддомен, а не `/status/`.

Перед запуском `08-setup-automation.sh` (или после — просто доступ не
заработает до этого): добавить DNS A-запись `status.astreatime.ru` → IP
сервера.

При первом запуске скрипт сам генерирует логин/пароль для basic-auth и
печатает пароль в терминал один раз — сохраните его сразу, повторно нигде
не выводится (хранится только bcrypt-хэш).

После установки:

1. Открыть `http://status.astreatime.ru`, ввести basic-auth логин/пароль,
   пройти мастер первого запуска Uptime Kuma (создать админ-аккаунт — это
   отдельная сущность от basic-auth, второй слой).
2. Add New Monitor → HTTP(s) → URL `https://www.astreatime.ru/health` →
   Friendly Name `astro api` → интервал проверки на вкус (60s достаточно).
3. Settings → Notifications → Add New Notification Type → Telegram → вписать
   тот же `TELEGRAM_BOT_TOKEN`, что и в `.env`, и `TELEGRAM_SUPPORT_CHAT_ID`
   (или отдельный чат/канал, если не хотите мешать с прочими алертами) →
   привязать это уведомление к монитору `astro api`.

## Автоматические бэкапы и чистка образов

`08-setup-automation.sh` также ставит два systemd-таймера (юниты — в
`systemd/`, устанавливаются в `/etc/systemd/system/`):

- `astro-backup.timer` → `07-backup-cron.sh` ежедневно в 03:30 (+ случайная
  задержка до 15 мин): `pg_dump` → `gzip` → шифрование `age` → проверка
  (`gzip -t` + `pg_restore -l`, архив не восстанавливается, только читается
  оглавление) → ротация: дампы старше 14 дней удаляются. При любой ошибке —
  сообщение в Telegram через `TELEGRAM_BOT_TOKEN`/`TELEGRAM_SUPPORT_CHAT_ID`
  из `.env`.

  Предусловие: пакет `age` и `BACKUP_AGE_RECIPIENTS` в `.env` — оба ставит
  идемпотентно `08-setup-automation.sh`. Если получателя в `.env` ещё нет,
  скрипт сам генерирует пару `age-keygen` и печатает приватный ключ в
  терминал **один раз** (как пароль basic-auth выше) — на сервере он не
  сохраняется, только публичная часть уходит в `BACKUP_AGE_RECIPIENTS`.

  **Приватный ключ обязан храниться вне сервера** (менеджер паролей, свой
  диск) — сохраните его сразу же при первом выводе. Второй раз он нигде не
  печатается и не восстанавливается; если ключ потерян, все существующие
  `.dump.gz.age` расшифровать уже нельзя. Раз в квартал стоит руками
  проверять, что сохранённый ключ действительно расшифровывает свежий бэкап
  (команда — в комментарии в конце `07-backup-cron.sh`).
- `astro-prune.timer` → `prune-and-diskcheck.sh` еженедельно:
  `docker image prune -af --filter until=168h` (не трогает образы младше
  недели и образы, на которые ссылается хоть один контейнер) + если
  свободного места на диске меньше 20% — сообщение в Telegram.

Проверить статус: `systemctl list-timers 'astro-*'`,
`journalctl -u astro-backup.service`, `journalctl -u astro-prune.service`.

**Известный риск: нет выгрузки за пределы хоста.** `BACKUP_S3_TARGET` в
`.env.example` пуст по умолчанию, и на проде пока не задан — зашифрованные
дампы лежат только на том же диске, что и сама БД. Отказ или потеря этого
диска уносит базу и все бэкапы одновременно, шифрование от этого не спасает.
Не устранено, отдельная задача — завести `BACKUP_S3_TARGET` (rclone remote
или s3-совместимый бакет) и подтвердить, что `07-backup-cron.sh` реально
туда выгружает.

## Файлы

- `docker-compose.yml` — прод-стек: postgres, redis, api, bot, uptime-kuma
- `.env.example` — скопировать в `.env`, заполнить реальными значениями
- `frontend.env.example` — скопировать в `frontend.env`, build-time секреты фронта
- `app/` — сюда клонируется репозиторий (build context для api/bot, источник для сборки фронта)
- `frontend/` — сюда кладётся собранный `dist/` для nginx на хосте (root-овый: см. ниже)
- `nginx-backup/` — копии конфигов nginx перед перезаписью, последние 10 прогонов
- `.frontend-deployed-rev` — коммит последнего успешно доставленного фронтенда
- `nginx/astreatime.conf` — конфиг основного сайта для nginx на хосте
- `nginx/status.astreatime.conf` — конфиг Uptime Kuma (basic-auth) для nginx на хосте
- `systemd/` — юниты таймеров бэкапа и чистки образов
- `backups/` — дампы БД и диагностические отчёты
- `03-db-restore.sh` — перенос БД с Railway
- `04-frontend-deploy.sh` — сборка и публикация фронтенда + nginx
- `05-update.sh` — повседневное обновление одной командой (используется и вручную, и из CI)
- `06-diag.sh` — диагностический снимок состояния
- `07-backup-cron.sh` — ежедневный бэкап БД (запускается через `astro-backup.timer`)
- `08-setup-automation.sh` — установщик Uptime Kuma + systemd-таймеров
- `prune-and-diskcheck.sh` — еженедельная чистка образов + проверка места (через `astro-prune.timer`)
