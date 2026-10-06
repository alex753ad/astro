# План: кэш — в отдельный Redis (до включения `sky_event` всем)

Статус: план, кода нет (06.10.2026). Сначала — `used_memory` с прода (владелец).

Почему: прод-Redis один (DB 0) на всё — кэши, очереди Celery, лимиты, коды входа, токены; maxmemory нет (noeviction), контейнер `mem_limit: 512m` — рост кэша кончится OOM-kill всего Redis, а не вытеснением.

- **Что уходит в кэш-Redis** — только пересчитываемое бесплатно: `RedisCache` с префиксами `sky`, `feed`, `transit`, `chat_transits`, `geo` (и метка `sky:warm-year:*`). **Остаются в основном:** `interp` (там и прогнозы дня/фазы — платные тексты модели), `transit_interp` (платный разбор), `share:quote`, `rag:hist`, всё не-кэшевое (OTP, `login:fail`, `jwt:denied`, `sse:ticket`, `online`, `active`, `ai_budget`, лимиты slowapi, Celery, `astro:*`). Вытеснение платного текста = повторная оплата модели.
- **Конфиг (compose, `command:` — CONFIG отключён):** новый сервис `redis-cache`: `redis-server --requirepass ${REDIS_PASSWORD} --rename-command CONFIG "" --maxmemory 200mb --maxmemory-policy allkeys-lru --save ""` (без сохранения на диск — кэш), `mem_limit: 256m`. Основной: добавить `--maxmemory 384mb --maxmemory-policy noeviction` (запас до 512m на fork при RDB-снимке).
- **Код:** `settings.cache_redis_url` (env `CACHE_REDIS_URL`, по умолчанию = `REDIS_URL` — без переменной ничего не меняется); `RedisCache(prefix, ttl, url=...)` — кэш-префиксы выше берут `cache_redis_url`. Тест: без переменной — тот же URL.
- **Переключение без потери данных** (переносятся только пересчитываемые кэши):
  1. PR: сервис `redis-cache` в compose (пока не используется) + код с `CACHE_REDIS_URL`; деплой — ничего не меняется.
  2. Скрипт `scripts/cache_redis_on.sh` (с согласия владельца, одна команда): `CACHE_REDIS_URL=redis://:…@redis-cache:6379/0` в `.env`, пересоздать `api`, `worker`, `beat`. Новый кэш пуст — считается заново, `sky` дозаполнит ежечасный прогрев.
  3. Скрипт очистки старых префиксов в основном Redis — `SCAN` + `DEL` (не `KEYS`), иначе они доживут TTL (до 30 дней).
  4. `--maxmemory` основного — отдельно, в тихое время: пересоздание контейнера; перед ним `redis-cli SAVE` (SAVE не отключён), очереди Celery переживут через RDB.
