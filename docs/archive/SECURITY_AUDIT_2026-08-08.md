# Аудит безопасности — Astrea Timeline

**Дата:** 8 августа 2026
**Объём:** backend (FastAPI), frontend (React), инфраструктура (Docker/Nginx/VPS), CI/CD, история git на GitHub
**Репозиторий:** `https://github.com/alex753ad/astro.git`

---

## Резюме

Кодовая база уже прошла серьёзную работу по безопасности (ветка `security/remediation`): есть защита от BOLA/IDOR, ротация JWT-секрета, версионирование сессий, денилист токенов, блокировка перебора паролей, идемпотентность платёжного вебхука, выравнивание ответов против enumeration-атак, fail-closed логика доверенных прокси. SQL-инъекций, `eval`/`exec`, SSRF и XSS в клиенте не обнаружено.

Основные проблемы лежат в трёх плоскостях: **утёкшие в публичную историю git секреты**, **fail-open паттерн авторизации служебных эндпоинтов** и **отсутствующий слой защиты на уровне Nginx** (заголовки, TLS-политика, rate limiting).

| Уровень | Кол-во |
|---|---|
| 🔴 Критический | 2 |
| 🟠 Высокий | 5 |
| 🟡 Средний | 11 |
| 🔵 Низкий | 6 |

---

# 🔴 КРИТИЧЕСКИЕ

## C-1. Действующие секреты в публичной истории git

**Что найдено.** Скрипт `cleanup_git_history.sh` был выполнен и вычистил из истории `env`, `log.json`, `astro_search.session` и др. — этих файлов в истории больше нет. **Но `.env.example` вычищен не был**, а в нём коммитились реальные значения:

| Коммит | Файл | Секрет |
|---|---|---|
| `9690bab` (initial commit, 10.04.2026) | `.env.example` | `OPENAI_API_KEY=sk-proj-Y03pfX_HIG-…` — полноценный рабочий ключ (169 символов) |
| `c086efa` («security: CORS from env, JWT rotation…») | `.env.example` | `JWT_SECRET=ZKT87rW7BXK5AxBBZkb18sxS7Kfl…` |

Оба коммита проверены — **являются предками `origin/main`**, то есть находятся на GitHub и доступны через `git log -p`, GitHub API и любой форк/зеркало. Парадоксально, но именно коммит, добавивший ротацию JWT-секрета, и опубликовал сам секрет.

**Подтверждено сравнением хешей:** значение `JWT_SECRET` из утёкшего коммита `c086efa` **побайтово совпадает** с `JWT_SECRET` в текущем локальном `.env`. Прод-файл `deploy/opt-astro/.env` содержит другое значение (хеш отличается) — прод, скорее всего, не затронут, но dev/staging подписывают токены публично известным ключом.

**Последствия.**
- Кто угодно подписывает валидный access-токен с произвольными `sub`, `email`, `tier: "premium"`, `is_admin` — полный обход аутентификации и тарификации в любом окружении, где используется этот секрет.
- OpenAI-ключ: неограниченный расход на чужой счёт до момента отзыва.

**Решение.**
1. **Немедленно ротировать оба секрета**, независимо от того, где они используются:
   - OpenAI: отозвать ключ в platform.openai.com → API keys → Revoke. Проверить Usage за апрель–август на аномалии.
   - `JWT_SECRET`: сгенерировать новый `python -c "import secrets; print(secrets.token_urlsafe(48))"`, старый положить в `JWT_SECRET_PREV` на 7 дней (механизм уже реализован в `backend/auth/jwt.py`), затем убрать.
   - Заодно ротировать всё, что когда-либо лежало в вычищенных файлах (`env`, `log.json`): Anthropic, DeepSeek, Resend, Robokassa Password1/Password2, Google OAuth secret, Telegram bot token, пароль Postgres. Filter-repo убирает файлы из истории, но не отменяет факт, что они были опубликованы.
2. **Дочистить историю** — дописать в `cleanup_git_history.sh` и выполнить повторно:
   ```
   git filter-repo --force --path .env.example --invert-paths
   ```
   либо точечно через `--replace-text` со списком утёкших значений. После — `git push --force --all` и `--force --tags`.
3. **Важно:** GitHub сохраняет «висячие» объекты в форках и кэше веб-интерфейса даже после force-push. Открыть тикет в GitHub Support с просьбой удалить unreachable-объекты, либо (надёжнее) удалить репозиторий и создать заново из чистого состояния.
4. **Профилактика:**
   - Включить GitHub Secret Scanning + Push Protection (Settings → Code security).
   - Добавить `gitleaks` в CI как блокирующий шаг:
     ```yaml
     - uses: gitleaks/gitleaks-action@v2
       env: { GITHUB_TOKEN: "${{ secrets.GITHUB_TOKEN }}" }
     ```
   - Локальный pre-commit хук с `gitleaks protect --staged`.
   - Правило: `.env.example` содержит **только** имена переменных и явные плейсхолдеры (`sk-...`, `<generate-me>`). Добавить в CI проверку, что в `.env.example` нет строк длиннее 40 символов после `=`.

---

## C-2. Fail-open авторизация служебных эндпоинтов

**Что найдено.** Шесть публично доступных (`/api/…`, проксируются Nginx) эндпоинтов используют один и тот же паттерн:

```python
secret = os.getenv("INTERNAL_SECRET", "")
if secret and x_internal_secret != secret:      # ← если secret == "" — проверки НЕТ
    raise HTTPException(403, "Forbidden")
```

Места:

| Файл:строка | Эндпоинт | Что даёт злоумышленнику |
|---|---|---|
| `backend/pilot/router.py:64` | `POST /api/v1/internal/pilot-token` | **Выпуск pilot-токена → эскалация до `tier="premium"` на 30 дней** |
| `backend/onboarding_router.py:75` | `POST /api/v1/internal/onboarding-emails` | Массовая рассылка через Resend |
| `backend/onboarding_router.py:156` | `POST /api/v1/internal/weekly-digest` | Массовая рассылка |
| `backend/onboarding_router.py:170` | `POST /api/v1/internal/lunar-returns` | Постановка Celery-задач |
| `backend/push/cron.py:495` | `POST /api/v1/internal/push-tick` | Массовые push-уведомления |
| `backend/pilot/cron.py:256` | `POST /api/v1/internal/pilot-tick` | Массовая рассылка |

Цепочка эскалации: `POST /internal/pilot-token {"tg_user_id": "<любой>"}` → получить `token` → зарегистрироваться → `POST /api/v1/pilot/claim {"token": …}` → `user.tier = "premium"`, доступ к CRM, PDF-брендингу, 100 AI-интерпретаций/мес. Ограничение `_tg_already_piloted` обходится подстановкой нового произвольного `tg_user_id`.

**Текущий статус:** в `deploy/opt-astro/.env` строка 111 `INTERNAL_SECRET` **заполнена**, то есть прод сейчас закрыт. Но защита держится на наличии одной переменной окружения: любой новый инстанс, staging, локальный запуск с прод-БД или потерянная при рефакторинге `.env`-строка мгновенно открывают всё перечисленное. Это не «потенциальная» проблема — это отложенная.

**Решение.**
1. Заменить fail-open на fail-closed и вынести в единую зависимость (`backend/authz.py`):
   ```python
   import hmac, os
   from fastapi import Depends, Header, HTTPException

   def require_internal_secret(x_internal_secret: str = Header(default="")) -> None:
       secret = os.getenv("INTERNAL_SECRET", "")
       if not secret:
           raise HTTPException(503, "Internal endpoints disabled")   # не 403 — это ошибка конфигурации
       if not hmac.compare_digest(x_internal_secret, secret):
           raise HTTPException(403, "Forbidden")
   ```
   и применить как `dependencies=[Depends(require_internal_secret)]` во всех шести местах. `hmac.compare_digest` заодно убирает утечку по таймингу при посимвольном сравнении.
2. Добавить проверку на старте приложения — рядом с существующим guard'ом `JWT_SECRET` в `backend/main.py:258`:
   ```python
   if not (settings.debug or settings.testing) and not os.getenv("INTERNAL_SECRET"):
       raise RuntimeError("INTERNAL_SECRET не задан — служебные эндпоинты остались бы открытыми")
   ```
3. Второй рубеж: закрыть префикс на уровне Nginx, раз эти маршруты вызываются только с самого сервера:
   ```nginx
   location /api/v1/internal/ { allow 127.0.0.1; deny all; }
   ```
4. Регрессионный тест: запрос к каждому `/internal/*` без заголовка при непустом и при пустом `INTERNAL_SECRET` — в обоих случаях не 2xx.

---

# 🟠 ВЫСОКИЕ

## H-1. Полное отсутствие security-заголовков в Nginx

**Что найдено.** `deploy/opt-astro/nginx/astreatime.conf` не выставляет ни одного защитного заголовка. Отсутствуют: `Strict-Transport-Security`, `Content-Security-Policy`, `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`. Приложение — SPA, которое хранит JWT в `localStorage` (см. H-3), поэтому CSP здесь не косметика, а основной барьер против кражи токена при XSS. Отсутствие HSTS оставляет окно для SSL-stripping при первом заходе, отсутствие `X-Frame-Options`/`frame-ancestors` — для clickjacking на формах оплаты и удаления аккаунта.

**Решение.** В `server`-блок 443:
```nginx
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;
add_header X-Content-Type-Options    "nosniff" always;
add_header X-Frame-Options           "DENY" always;
add_header Referrer-Policy           "strict-origin-when-cross-origin" always;
add_header Permissions-Policy        "geolocation=(), microphone=(), camera=(), payment=()" always;
add_header Content-Security-Policy   "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self' https://*.sentry.io https://accounts.google.com; frame-src https://accounts.google.com; base-uri 'self'; form-action 'self'; frame-ancestors 'none'; object-src 'none'" always;
```
Замечания по внедрению:
- `always` обязателен — иначе заголовки не попадут в ответы 4xx/5xx.
- `add_header` в дочернем `location` **отменяет все родительские** — продублировать блок в `location /assets/` и `location = /index.html`, либо вынести в `include /etc/nginx/snippets/security-headers.conf`.
- CSP выкатывать через `Content-Security-Policy-Report-Only` на 1–2 недели, собрать нарушения, потом переключить. Инлайновые `style=` в компонентах потребуют `'unsafe-inline'` для `style-src` (допустимо) — но `script-src` держать без него.
- HSTS `preload` добавлять только после подтверждённой работы всех поддоменов по HTTPS (см. H-5).

## H-2. Uptime Kuma: basic-auth поверх незашифрованного HTTP

**Что найдено.** `deploy/opt-astro/nginx/status.astreatime.conf` объявляет только `listen 80` без TLS и без редиректа на HTTPS, но при этом требует `auth_basic`. Логин и пароль администратора мониторинга передаются по сети в base64 открытым текстом при каждом запросе. Перехват в любой промежуточной сети (Wi-Fi, провайдер, транзит) даёт доступ к панели Uptime Kuma — а это внутренняя топология, адреса эндпоинтов, история инцидентов и, при её конфигурации, вебхуки уведомлений.

**Решение.**
1. Выпустить сертификат: `certbot --nginx -d status.astreatime.ru`.
2. Переписать вхост по образцу основного: 80 → 301 на HTTPS, весь `location /` с basic-auth перенести в `listen 443 ssl`.
3. Сменить пароль в `/etc/nginx/.htpasswd-status` — прежний считать скомпрометированным.
4. Ещё надёжнее для служебной панели: ограничить по IP (`allow <ваш IP>; deny all;`) или убрать из публичного DNS и ходить через SSH-туннель `ssh -L 3001:127.0.0.1:3001`.

## H-3. JWT (access + refresh) в `localStorage`

**Что найдено.** `frontend/src/api/client.js` хранит `astro_access_token` и refresh-токен в `localStorage`. Refresh живёт 7 дней (`jwt_refresh_token_expire_days: 7`). `localStorage` доступен любому JS в источнике, включая внедрённый через XSS или скомпрометированную npm-зависимость на этапе сборки. Кража refresh-токена = недельный доступ к аккаунту, при этом сам токен передаётся в теле запроса, а не в cookie, поэтому HttpOnly-защиты нет по определению.

**Решение (по возрастанию стоимости).**
1. **Дёшево и сразу:** внедрить CSP из H-1 — она перекрывает основной вектор доставки XSS-полезной нагрузки.
2. **Правильно:** перевести **refresh**-токен в cookie `HttpOnly; Secure; SameSite=Strict; Path=/api/v1/auth/refresh`. Access-токен оставить в памяти JS (обычная переменная в модуле/контексте, не `localStorage`) — он живёт 15 минут и восстанавливается через `/refresh`. Требует правки `client.js`, `/login`, `/refresh`, `/logout` и `allow_credentials` уже включён в CORS.
3. Механизм отзыва уже есть и работает — `token_version` (`backend/auth/dependencies.py:42`) и денилист по `jti`. Стоит добавить в `/api/v1/auth/me` показ активных сессий и кнопку «выйти везде» (эндпоинт `/logout-all` уже реализован, `auth/router.py:608`).

## H-4. Robokassa в тестовом режиме в прод-окружении

**Что найдено.** `deploy/opt-astro/.env`:
```
ROBOKASSA_MERCHANT_LOGIN=      ← пусто
ROBOKASSA_PASSWORD1=<задан>
ROBOKASSA_PASSWORD2=<задан>
ROBOKASSA_IS_TEST=true
```
`create_payment_url` подставляет `IsTest=1` в ссылку оплаты (`robokassa_service.py:89`). Тестовый режим Robokassa проводит платёж без реального списания, но вебхук `/api/v1/payments/robokassa/result` приходит настоящий и `activate_subscription` выдаёт полноценный тариф. Пустой `MERCHANT_LOGIN` указывает, что файл, возможно, заполнен не до конца, — но в текущем виде это либо неработающая оплата, либо бесплатные подписки.

**Решение.**
1. Проверить фактическое содержимое `/opt/astro/.env` на сервере. На проде: `ROBOKASSA_IS_TEST=false`, `MERCHANT_LOGIN` заполнен.
2. Сделать ошибку невозможной — guard на старте рядом с проверкой `JWT_SECRET`:
   ```python
   if not (settings.debug or settings.testing):
       if settings.robokassa_is_test:
           raise RuntimeError("ROBOKASSA_IS_TEST=true в проде — подписки выдавались бы без оплаты")
       if not settings.robokassa_merchant_login:
           raise RuntimeError("ROBOKASSA_MERCHANT_LOGIN не задан")
   ```
3. Поменять дефолт в `backend/config.py:65` с `robokassa_is_test: bool = True` на `False` — небезопасный режим должен требовать явного включения, а не наоборот.

## H-5. Rate limiting покрывает ~15% эндпоинтов

**Что найдено.** Из ~141 маршрута декоратор `@limiter.limit` стоит на 22. Полностью без ограничений остались роутеры `crm`, `payments`, `share`, `portal`, `rag`, `pilot`, `push`, `admin`, `promo`, `onboarding`, `exit_survey`. На уровне Nginx `limit_req_zone` не настроен вовсе. Наиболее чувствительные:

| Эндпоинт | Авторизация | Риск |
|---|---|---|
| `POST /api/v1/auth/register/email/send-code` | нет | **Email-бомбинг.** Троттлинг есть только по адресу получателя (`_resend_key`, 60 с). Перебор разных адресов в цикле → тысячи писем через Resend → счёт, попадание домена в спам-листы, потеря доставляемости для всей рассылки |
| `POST /api/v1/chart/{id}/rag-chat` | Pro+ | Неограниченный расход на LLM. Не списывается в `UsageCounter`, `budget_tracker` в этом пути не проверяется. Один аккаунт за 1990 ₽/мес может сжечь дневной бюджет |
| `GET /share/{token}/card.png` | нет, публичный | Генерация PNG 1200×630 + вызов LLM за подписью. Кэш по токену есть, но первый запрос на каждый новый токен — дорогой. CPU-исчерпание |
| `GET /api/v1/portal/{token}` | нет, публичный | Отдаёт ПДн клиента (дата, место рождения). Токен — `token_urlsafe(24)`, перебор нереален, но нет и защиты от массового опроса утёкшего списка |

**Решение.**
1. Глобальный дефолт вместо точечных декораторов — в `backend/main.py`:
   ```python
   limiter = Limiter(key_func=client_ip, default_limits=[settings.rate_limit_anon],
                     storage_uri=settings.rate_limit_storage_uri or settings.redis_url)
   ```
   Точечные `@limiter.limit` останутся как переопределения там, где нужен другой порог.
2. Явные лимиты на перечисленное: `send-code` — `3/hour` по IP **и** отдельный счётчик по подсети /24; `rag-chat` — `20/hour` по `user.id` (ключ через `key_func`, не по IP); `card.png` — `30/minute`.
3. Завести `/rag-chat` в существующую систему квот: списывать в `UsageCounter` и проверять `budget_tracker.is_within_budget()` перед вызовом модели — инфраструктура уже написана в `backend/interpretation/router.py:321`.
4. Второй рубеж в Nginx, он дешевле приложения:
   ```nginx
   limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;
   limit_req_zone $binary_remote_addr zone=auth:10m rate=1r/s;
   location /api/            { limit_req zone=api  burst=20 nodelay; ... }
   location /api/v1/auth/    { limit_req zone=auth burst=5;          ... }
   ```

---

# 🟡 СРЕДНИЕ

## M-1. Идемпотентность платежей отключается при недоступности Redis

`backend/payments/payments_router.py:100`:
```python
try:
    first_time = await get_redis().set(f"robokassa:inv:{inv_id}", "1", nx=True, ex=...)
except Exception as exc:
    logger.error("Robokassa idempotency store failed, proceeding: %s", exc)
    first_time = True          # ← fail-open
```
При недоступном Redis anti-replay исчезает: перехваченный (или просто повторно отправленный) вебхук с валидной подписью продлевает подписку сколько угодно раз. Признак существования проблемы: единственный источник истины о платеже — Redis с TTL 90 дней, а не БД.

**Решение.** Перенести идемпотентность в Postgres — таблица `payment_events(inv_id PK, user_id, tier, period, amount, created_at)` со вставкой в той же транзакции, что и `activate_subscription`; `IntegrityError` на дубликат = уже обработано. Redis оставить как быстрый предфильтр. Заодно появится аудит платежей, которого сейчас нет вообще (`inv_id` генерируется `random.randint` и нигде не сохраняется до вебхука).

## M-2. Сравнение секретов без защиты от тайминг-атак

- `robokassa_service.py:112` — `if sig_got != sig_exp`
- шесть мест с `x_internal_secret != secret` (см. C-2)

**Решение.** Везде `hmac.compare_digest(a, b)`. Практическая эксплуатация по сети маловероятна, но замена — одна строка.

## M-3. Два независимых механизма админ-доступа

`backend/admin/admin_router.py:16` использует флаг `users.is_admin` в БД — и в комментарии прямо описано, почему отказались от прежней схемы. Но `backend/payments/payments_router.py:131` по-прежнему проверяет список из `os.getenv("ADMIN_EMAIL")`, причём эндпоинт `POST /api/v1/payments/admin/set-tier` умеет выдать **любому пользователю любой тариф на 10 лет**. Два источника истины о правах — гарантированное расхождение: отзыв прав через `is_admin=false` не закроет доступ владельцу почты из `ADMIN_EMAIL`.

**Решение.** Заменить проверку в `payments_router.py` на `Depends(require_admin)` из `admin_router.py`, убрать чтение `ADMIN_EMAIL` из кода. Отдельно: писать все вызовы `set-tier` и `delete_user` в таблицу аудита (кто, кого, когда, что изменил).

## M-4. Зависимости без фиксации версий

`pyproject.toml` — все зависимости указаны как `>=`, lock-файла нет. Docker-образ собирается `pip install -e "."` без `--require-hashes`, при недоступности `pyproject.toml` откатывается на второй `pip install` со списком пакетов вообще без версий (`Dockerfile:15`). Каждая пересборка тянет другой набор версий; воспроизвести упавший прод-образ невозможно; компрометация любого пакета в цепочке попадает в прод при следующем деплое.

Точечно: **`python-jose>=3.3.0`** — библиотека подписи JWT, на которой держится вся аутентификация. В 3.3.0 присутствуют CVE-2024-33663 (algorithm confusion) и CVE-2024-33664 (DoS через JWE-бомбу), закрыты в 3.4.0. Диапазон `>=3.3.0` допускает установку уязвимой версии. Также `bcrypt>=3.2.0,<4.0.0` — верхняя граница держит устаревшую ветку.

**Решение.**
1. Зафиксировать всё: `pip-compile` (pip-tools) или `uv pip compile pyproject.toml -o requirements.lock`, в Dockerfile — `pip install --no-cache-dir -r requirements.lock`.
2. Убрать fallback-ветку `|| pip install fastapi uvicorn …` из `Dockerfile:14` — она молча собирает неизвестно что при ошибке основной установки.
3. Поднять нижнюю границу: `python-jose[cryptography]>=3.4.0`. Стратегически — рассмотреть переход на `PyJWT`, который поддерживается активнее.
4. Пересмотреть пин `bcrypt<4.0.0` — он был нужен для старого passlib; на актуальном passlib ограничение снимается.
5. В CI добавить `pip-audit` и `npm audit --audit-level=high`, включить Dependabot.

## M-5. Отсутствие проверок безопасности в CI

`.github/workflows/` содержит только pytest, alembic-check и сборку фронтенда. Нет SAST, нет сканирования зависимостей, нет поиска секретов — то есть утечка из C-1 не была бы замечена и сегодня.

**Решение.** Добавить джобы: `gitleaks` (блокирующий), `pip-audit`, `npm audit`, `bandit -r backend/ -ll`, `ruff check` (уже в dev-зависимостях, но в CI не запускается).

## M-6. Деплой: незапиненные Actions и отсутствие ограничения прав

`.github/workflows/ci.yml`, джоб `deploy`:
- `uses: appleboy/ssh-action@v1` — плавающий тег. Владелец репозитория действия (или тот, кто получит к нему доступ) может переместить тег на произвольный код, который выполнится **с приватным SSH-ключом от прод-сервера** в переменной `secrets.SSH_PRIVATE_KEY`.
- Блок `permissions:` не объявлен — `GITHUB_TOKEN` получает права по умолчанию из настроек репозитория (потенциально `write-all`).
- Нет `environment:` с required reviewers — любой push в `main` немедленно уходит на прод.

**Решение.**
1. Запинить все actions на полный SHA коммита: `uses: appleboy/ssh-action@<40-символьный-sha>  # v1.2.0`. Обновления доверить Dependabot (`package-ecosystem: github-actions`).
2. Добавить в начало workflow `permissions: contents: read`.
3. Обернуть деплой в `environment: production` с required reviewer.
4. Включить branch protection на `main`: запрет force-push, обязательный PR-ревью, обязательные статус-чеки.
5. SSH-ключ деплоя ограничить в `~/.ssh/authorized_keys` на сервере: `command="/opt/astro/05-update.sh",no-agent-forwarding,no-port-forwarding,no-pty ssh-ed25519 …` — тогда даже украденный ключ не даёт интерактивный шелл.

## M-7. Диагностическая информация в `/health/db`

`backend/main.py:365` возвращает клиенту текст исключения: `db_status = f"error: {e}"`. Исключения SQLAlchemy/psycopg2 регулярно содержат имя хоста, порт, имя БД и пользователя, иногда — фрагмент DSN. Эндпоинт `/health` проксируется Nginx наружу.

**Решение.** Наружу — только `{"database": "error"}`, подробности в `logger.exception`. Полную диагностику вынести в `/health/db/detailed` под `require_admin` либо `allow 127.0.0.1` в Nginx.

## M-8. Персональные данные в логах открытым текстом

В `backend/auth/router.py` и `email_service.py` email пользователя пишется в лог в ~10 местах (`"New user via email OTP: %s"`, `"Password reset completed: %s"` и др.). Логи уходят в json-file драйвер Docker (`docker-compose.yml`, 10 МБ × 3), читаются любым, у кого есть доступ к сокету Docker или к диску, попадают в бэкапы. Для сервиса, обрабатывающего ПДн граждан РФ (дата, время и место рождения — это ПДн), это претензия по 152-ФЗ.

**Решение.** Логировать `user.id` (UUID) вместо адреса; где адрес нужен для расследования — маскировать (`a***@gmail.com`) или хешировать. В Sentry `send_default_pii=False` уже выставлен и `before_send` определён — стоит расширить фильтр на email в `extra`/`breadcrumbs`.

## M-9. Prompt injection в RAG-чате

`backend/interpretation/rag_router.py:274` — массив `history` приходит целиком от клиента, включая сообщения с `role: "assistant"`:
```python
+ [{"role": m["role"], "content": m["content"]} for m in history
   if m.get("role") in ("user", "assistant") and m.get("content")]
```
Клиент подделывает реплики «ассистента» и задаёт модели любое поведение: извлечение системного промпта, содержимого `knowledge_base.json`, авторских интерпретаций из `AstrologerInterpretation` (платный контент Premium), генерация произвольного текста под брендом Astrea.

**Решение.** Хранить историю диалога на сервере (Redis по `chat_id`, TTL сессии), от клиента принимать только `chat_id` и новый вопрос. Если это слишком дорого сейчас — минимум: ограничить суммарную длину истории в символах, а не только числом сообщений (`MAX_HISTORY`), и добавить в системный промпт явную инструкцию игнорировать попытки переопределить роль. Второе — паллиатив, первое — решение.

## M-10. Nginx: TLS-политика и раскрытие версии

- `ssl_ciphers HIGH:!aNULL:!MD5` — устаревшая формулировка, пропускает CBC-наборы и не отражает современные рекомендации.
- Нет `ssl_session_cache`, `ssl_session_timeout`, `ssl_stapling` — потери и по безопасности, и по скорости рукопожатия.
- `server_tokens` не выключен — в каждом ответе и на страницах ошибок отдаётся точная версия nginx.
- Нет `default_server`-блока, отбивающего запросы с неизвестным `Host`, при том что наверх передаётся `proxy_set_header Host $host` — открывает Host-header injection (отравление ссылок в письмах, кэша).

**Решение.**
```nginx
server_tokens off;
ssl_protocols TLSv1.2 TLSv1.3;
ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305;
ssl_prefer_server_ciphers off;          # при TLS1.3 приоритет клиента корректнее
ssl_session_cache shared:SSL:10m;
ssl_session_timeout 1d;
ssl_session_tickets off;
ssl_stapling on;
ssl_stapling_verify on;

server { listen 80 default_server; listen 443 ssl default_server;
         ssl_reject_handshake on; return 444; }
```
Плюс `TrustedHostMiddleware` в FastAPI как второй рубеж. Проверить результат на ssllabs.com.

## M-11. Ужесточение контейнеров

`docker-compose.yml`:
- Redis запущен без `requirepass` и без ACL. Не опубликован наружу (`ports` не объявлены) и живёт в отдельной сети — но в нём лежат SSE-тикеты, денилист JWT, счётчики лимитов и ключи идемпотентности платежей. Компрометация любого контейнера в `astro_net` даёт полный доступ.
- Ни у одного сервиса нет `security_opt: [no-new-privileges:true]`, `cap_drop: [ALL]`, `read_only: true`.
- Лимиты ресурсов заданы только для `uptime-kuma` (`mem_limit: 256m`). У `api`, `postgres`, `redis` их нет — одна утечка памяти кладёт весь хост.

**Решение.**
```yaml
redis:
  command: redis-server --requirepass ${REDIS_PASSWORD} --save 60 1 --loglevel warning
  # и REDIS_URL=redis://:${REDIS_PASSWORD}@redis:6379/0
api:
  security_opt: [ "no-new-privileges:true" ]
  cap_drop: [ ALL ]
  deploy: { resources: { limits: { memory: 1g, cpus: "1.5" } } }
```
Образ уже собирается под non-root пользователем (`Dockerfile:35`) — это сделано правильно.

---

# 🔵 НИЗКИЕ

## L-1. Токены сброса пароля и подтверждения email не привязаны к версии сессии

`create_password_reset_token` / `create_email_confirmation_token` не содержат claim `tv`, поэтому `logout-all` и смена пароля их не гасят. Для reset частично закрыто денилистом по `jti`, для email-подтверждения (24 часа) — нет. **Решение:** добавить `tv` в payload и проверять при разборе, как в `decode_token`.

## L-2. `random.randint` для номера счёта

`robokassa_service.py:71` — `inv_id = random.randint(1, 2_000_000_000)` на непредсказуемом, но некриптографическом ГПСЧ, без проверки уникальности (записи о счёте не существует, см. M-1). Коллизия при накоплении платежей ломает идемпотентность из M-1: второй платёж с тем же `inv_id` будет отброшен как дубль. **Решение:** автоинкремент в таблице `payment_events` или `secrets.randbelow(2_000_000_000)`.

## L-3. Публичные токены без срока в БД

Токены `share` и `portal` (`token_urlsafe(24..32)` — энтропия достаточная) не имеют поля срока в БД. Для `share` TTL хранится в Redis, причём `_ensure_not_expired` при недоступности Redis **fail-open** и явно это комментирует (`share_router.py:53`). Для `portal` (отдаёт ПДн клиента) срока нет вообще — только флаг `enabled`. **Решение:** колонка `expires_at` в таблице, проверка в SQL-запросе; Redis — только кэш.

## L-4. `Base.metadata.create_all()` на старте приложения

Отмечено как критичное в самом `deploy/opt-astro/README.md`: при первом старте на пустой БД схема создаётся в обход Alembic, `alembic_version` остаётся пустой, история миграций расходится с реальностью. Скорее проблема надёжности, но именно она обычно приводит к «временным» ручным правкам схемы на проде. **Решение:** обернуть вызов в `if settings.testing:` — на проде схему создаёт только `alembic upgrade head` (он и так вызывается в `05-update.sh`).

## L-5. Бэкапы без шифрования и без выноса за пределы хоста

`07-backup-cron.sh` кладёт `pg_dump | gzip` в `/opt/astro/backups` на том же сервере, ротация 14 дней. Дамп содержит все ПДн, bcrypt-хеши паролей и платёжную историю. Компрометация или отказ диска сервера = потеря и утечка одновременно. Отдельно: `get_env_var()` читает `TELEGRAM_BOT_TOKEN` из `.env` и передаёт в `curl` — токен виден в `ps` любому пользователю системы на время запроса. **Решение:** `gpg --encrypt` или `age` перед выгрузкой, копия в S3-совместимое хранилище (Timeweb Object Storage) с версионированием и отдельными ключами доступа, регулярная проверка восстановления. Токен передавать через `--data-urlencode` из файла или `curl --config`, а не в аргументах URL.

## L-6. Мусор в рабочем каталоге

В корне лежат `test.db` (300 КБ), `test_astro.db` (78 КБ), `:wq` (артефакт vim), `error.txt`, `push_notifications.patch`, `natal_chart.pdf`, `astro_channels.csv/json`, каталоги `.venv/`, `.vercel/`, `.pytest_cache/`. В git ничего из этого не попало (`.gitignore` покрывает `*.db`), но `git status` показывает неотслеживаемые `git`, `main`, `scp` — файлы нулевого размера от опечаток в командах. Риск в том, что при `git add -A` или неаккуратной правке `.gitignore` (что в истории уже случалось — коммит `726ede5` «снять .env* из .gitignore») содержимое БД уйдёт в репозиторий. **Решение:** почистить каталог; проверить `.gitignore` на предмет `*.db`, `*.sqlite3`, `.env*` с явными исключениями для `.example`.

---

# План работ

## Сегодня
1. **C-1** — отозвать OpenAI-ключ, ротировать `JWT_SECRET` через `JWT_SECRET_PREV`, ротировать остальные секреты из вычищенных файлов.
2. **H-4** — проверить `ROBOKASSA_IS_TEST` на боевом сервере.
3. **H-2** — сменить пароль Uptime Kuma, закрыть поддомен по IP до выпуска сертификата.

## На этой неделе
4. **C-1** — дочистить `.env.example` из истории, force-push, обращение в GitHub Support, включить Secret Scanning + Push Protection.
5. **C-2** — fail-closed для `INTERNAL_SECRET` + guard на старте + `allow 127.0.0.1` на `/api/v1/internal/`.
6. **H-1** — security-заголовки в Nginx, CSP в режиме Report-Only.
7. **H-5** — лимиты на `send-code`, `rag-chat`, `card.png`; `limit_req_zone` в Nginx.

## В течение месяца
8. **M-4, M-5, M-6** — lock-файл зависимостей, `python-jose>=3.4.0`, gitleaks/pip-audit/bandit в CI, пин actions по SHA, branch protection.
9. **H-3** — refresh-токен в HttpOnly-cookie.
10. **M-1, M-3** — таблица `payment_events`, единая проверка админ-прав, аудит-лог.
11. **M-9** — история RAG-чата на сервере.
12. **M-10, M-11, M-8** — TLS-политика, ужесточение контейнеров, чистка ПДн из логов.

## Постоянно
13. Включить CSP из Report-Only в блокирующий режим после сбора нарушений.
14. **L-5** — шифрование и вынос бэкапов, проверка восстановления раз в квартал.
15. Повторный аудит после закрытия критических и высоких пунктов.

---

## Что сделано хорошо

Чтобы отчёт не создавал ложного впечатления — вот что в проекте уже сделано на уровне, который встречается нечасто:

- **BOLA/IDOR** — `backend/authz.py` и `resolve_chart_access` последовательно отдают 404 вместо 403, не подтверждая существование чужих объектов. CRM полностью изолирована по `astrologer_id` — проверено по всем запросам в `crm/`.
- **SQL-инъекции** отсутствуют: везде ORM либо параметризованный `text()` с bind-параметрами.
- **User enumeration** закрыт грамотно: `/register/email/send-code` выравнивает и код ответа, и время выполнения (bcrypt считается в обеих ветках), и наличие троттлинга.
- **Перебор паролей** — двухуровневая защита: лимит по IP плюс `login_guard` по email, что закрывает распределённую атаку с ботнета.
- **Отзыв сессий** — `token_version` + денилист `jti` в Redis, с корректной обработкой legacy-токенов без claim.
- **X-Forwarded-For** обрабатывается fail-closed и справа налево — редко встречающаяся корректная реализация.
- **Политика паролей** учитывает 72-байтовое ограничение bcrypt и двухбайтовую кириллицу.
- **Rate-limit хранилище** в Redis, а не в памяти процесса — лимиты не умножаются на число воркеров.
- **CORS** — явные списки методов и заголовков, отказ стартовать при `"*"` вместе с `allow_credentials`.
- **Debug-роуты и legacy-регистрация** физически недоступны вне `DEBUG/TESTING`.
- **Контейнер** работает под non-root пользователем с явным UID.
- Комментарии в коде объясняют *почему* сделано так — по ним видно, что каждое из решений выше принималось осознанно, а не скопировано.
