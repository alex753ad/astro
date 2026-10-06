> Архив. Решение владельца 06.10.2026: пилотная программа остаётся как есть, ничего не удаляется; отменено только задание 4.11 аудита.

# Опись пилота (06.10.2026) — без удаления, ждёт «да» владельца

Пилот шире задания 4.11: 30 дней премиума через Telegram-бота, CRM «только чтение» для бывших пилотных, письма farewell / dormant 5-10-14 / опрос конца месяца, автопонижение до free, вкладка в админке. Строки — по HEAD 5c5b101 (возможен сдвиг).

⚠️ До удаления: если на проде есть пользователи с `pilot_started_at`, удаление `pilot/cron` снимет их автопонижение до free (`tasks.py:630,639` пилотных пропускает). Сначала — число таких на проде.

## Удалить
- Код: `backend/pilot/` целиком (`cron.py` — `_upcoming_windows`, farewell/dormant/downgrade/eom, `/internal/pilot-tick`; `router.py` — `/pilot/claim`, `/internal/pilot-token`); `backend/main.py:93-94,409-410` (подключение роутеров); `bot/pilot_bot.py` + `start.sh:12-15` + сервис `bot:` в `docker-compose.yml:105`, `deploy/opt-astro/docker-compose.yml:107`.
- Расписание: `celery_app.py:88-94` (`pilot-tick-hourly`), `tasks.py:67-79` (`tasks.pilot_tick`), `deploy/opt-astro/systemd/astro-pilot-tick.*` (+ отключить на VPS скриптом), `08-setup-automation.sh:24,196,209`, `deploy/opt-astro/README.md:89-91`.
- Письма: `email_service.py` — `send_pilot_farewell`, `send_dormant`, `send_end_of_month_survey` (зовёт только пилот).
- Env: `deploy/opt-astro/.env.example:142,149-155` (`PILOT_*`, `CONTINUE_PRO_*`).
- БД: модель `PilotToken` (`models.py:833-841`) + НОВАЯ миграция drop `pilot_tokens`. Старые миграции 034/035/036/044/068 не трогать.
- Тесты: `test_pilot_cron.py`, `test_pilot_claim_race.py`, `test_pilot_bot_network.py`; пилотные кейсы в `test_email_unsubscribe.py:26-27,173-191`, `test_email_window.py:186-193`, `test_internal_endpoints.py` (pilot-token / pilot-tick).
- Фронт: `components/PilotClaim.jsx`, `App.jsx:36,511`, `routes.js:199`.
- Docs: строки пилота в `docs/notifications.md`; 4.11 в `docs/audit_unified_model.md` — зачеркнуть, как 4.9/4.10.

## Неоднозначно — не трогать без решения
- `crm/access.py` (`_is_ex_pilot`, CRM «только чтение» бывшим пилотным), `crm/access_router.py` (`pilot_ended` — может читать фронт).
- `users.pilot_started_at` (`models.py:59`): от него зависят MRR-фильтр `admin/stats_router.py`, автопонижение, `crm/access`, тесты `test_admin_stats_subscriptions.py`, `test_yookassa.py:665-667`, бейдж «Пилот» в `AdminPage.jsx`.
- `users.tg_user_id` (`models.py:60`, уникальный индекс) — ставит только пилот; проверить прочие чтения.
- `exit_survey` моменты `dormant`/`end_of_month` (`exit_survey/router.py`, `ExitSurveyModal.jsx`) — по уже отправленным письмам ссылки ещё живут.
- Вкладка «Пилот» в `AdminPage.jsx` — в основном общие метрики (удержание, воронка, опросы); переименовать, убрать только карточку «Активировали пилот».
- `test_payment_flow.py:399` импортирует помощники из `test_pilot_claim_race.py` — перенести в conftest ДО удаления.
- `scripts/check_push_tick_channels.sh`, `scripts/check_support_bot.sh` (шаги 6–8 с ботом), `TASKS.md` (пункты контраста с `PilotClaim`).

## Оставить
- Комментарии в `payments/common.py`, `push/*`, `limiter.py`, `authz.py`, `notifications/telegram.py`, `metrics.py`, `models.py:782` — только переписать слова.
- Таблицы `Event`, `Feedback`, `ExitReason` (общие), история в `docs/HISTORY-*`, `docs/decisions.md`, `docs/archive/*`, `документация/`.
- Флагов пилота нет. `TELEGRAM_BOT_TOKEN` — нужен поддержке.

## Не пилот — оставить («режим почты» для приёмки)
Литерально «режим почты» в коде нет; ближайшее — режим флага `users` («Только эти почты»): `flags.py:1,46`, `admin/admin_router.py:178-215`, `AdminPage.jsx:1110,1160`, `docs/flags.md:12`. Окно писем 09–21 (`lifecycle_emails.email_window_open`) — общее. Если «режим почты» — другое, пришлите, где он.
