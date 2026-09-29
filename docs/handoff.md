# Передача работы — задание docs/task_current.md (обновлено 29.09.2026, днём)

Разделы 1–5 и 7 — на проде с утра 29.09. Потом три круга приёмки планера
(сообщения владельца 29.09) — тоже на проде: main `223dfa7`, деплой-прогон
36545189316 зелёный, `/health` 200, миграций не было. **Раздел 6 (PDF по
тарифам) не начат** — остановлено по условию владельца (контекст), план и
разведка ниже. Код — от свежего main в новой ветке; этот файл и
task_current.md в main не попадают.

## Что выкачено по приёмке планера 29.09 (для справки)

* «Ближайшие 30 дней» вместо таймлайна: рельс, окно от сегодня
  (`house_passages.compute_upcoming` + `/calendar/lunar` за 2 месяца,
  `lib/plannerDates.js`), месяц у первой даты, затухание справа, подпись по
  нажатию. Разбор — docs/feed.md, «Планер, 29.09.2026».
* Листание месяцев: free 0 / Вега 6 / Лира 12 / Орион 24 (`planner_months`,
  `tierCatalog.plannerMonthsAhead`, `offerRule` фича `planner_horizon`) —
  docs/tariffs.md, «Листание планера по месяцам».
* Тексты Луны и периодов: вычитка, строчная после двоеточия, сканер
  `test_planner_texts.py`; подсказки `forecast_prompt.py` без эзотерики,
  `GENERAL_CALENDAR_PROMPT_VERSION = 4`, тест `test_prompt_words.py`.
* Стенд веба: `frontend/web-preview.html`, `__preview__/WebPreview.jsx`
  (`?view=planner-free&tier=lite`), `shots.cjs` (нужен `PUP_DIR` — свой
  профиль Chrome, иначе запуск виснет), фикстура — скрипт
  `regen_fx.py` был в scratchpad: `build_planner(tier=…, with_upcoming=True)`
  по `chart_fixture.json` + `_compute_lunar_calendar` за 2 месяца.

## Ответы владельца по разделу 6 (действуют)

* Готовый PDF хранить на сервере 30 дней. Список «PDF-отчёты» в карточке
  карты (веб и приложение): дата, тариф, «Скачать». Готов — отметка в
  списке; ушёл со страницы — уведомление «PDF готов» (push, если включены;
  иначе при следующем заходе). Удаление через 30 дней автоматически; текст
  «Файл хранится 30 дней».
* Остальное — task_current.md, п. 6 (состав Веги/Лиры, кеш, каталог, тест,
  команда пересоздания разбора 80605fbf).

## Раздел 6 — разведка (29.09, код не писался)

* **Сейчас PDF синхронный**: `main.py` `start_pdf_generation`
  (`POST /chart/{id}/pdf`) берёт ПОСЛЕДНИЙ разбор без учёта тарифа; если
  разбора нет — генерирует через `check_interpretation_limit` +
  `commit_interpretation` (списывает квоту разборов — по заданию для PDF
  больше не списывать). Квота PDF: `check_pdf_limit` / `commit_pdf`.
  Рендер — `backend/natal_pdf.py` (`generate_pdf_bytes`, `_render`, `_Flow`,
  два прохода ради «стр. N из M»). Веб: `ChartPage.jsx` `runPdfDownload`
  (шлёт `wheel_png` — снимок колеса из браузера). Приложение: «Ещё» ведёт на
  сайт (TASKS п. 2 — скачивание в приложении не сделано, нужен плагин
  файла/«Поделиться»).
* `interpretations` (models.py:205): тарифа нет. `_save_chart_interpretation`
  НЕ пишет второй разбор, если первый есть, — при разборе «под тариф» это
  правило придётся развести (писать новую строку с тарифом).
* Глубина разбора — `TIER_FLAGS.interpretation_word_limit` (free 450, Вега
  800, Лира 2500, Орион 5000), `InterpretationRequest(tier=…)`.
* Celery есть (worker + beat в docker-compose), beat — `celery_app.py`
  `beat_schedule`; прямой вызов Swiss Ephemeris внутри задачи допустим.
* Последняя миграция — `066_calendar_export_chart` → следующая 067.

## Раздел 6 — предлагаемый план (владельцу не показывался)

1. Миграция 067: `interpretations.tier` (null у старых — глубину выводить по
   числу слов: высший тариф, где слов ≥ 0,7 × word_limit); таблица
   `pdf_reports` (id, user_id, chart_id, tier, status queued/running/ready/
   failed, progress, step, content bytea, created_at, ready_at, expires_at =
   +30 дней, seen_at, fingerprint); таблица `pdf_section_cache` (chart_id,
   key, content JSON, created_at): аспекты — ключ `aspects:v<версия>:<N>`,
   транзиты — `transits:<ГГГГ-ММ>:<тариф>`.
2. Ручки: `POST /chart/{id}/pdf-reports` (старт; при готовом отчёте с тем же
   fingerprint — вернуть его без списания), `GET /chart/{id}/pdf-reports`
   (список), `GET /pdf-reports/{id}` (статус/прогресс), `GET
   /pdf-reports/{id}/file`. Старый `POST /chart/{id}/pdf` оставить для
   старых APK.
3. Celery-задача сборки: разбор (свой тариф или новый без списания квоты,
   с записью тарифа) → аспекты (5/7 самых точных, одним запросом DeepSeek,
   кеш) → транзиты на 6/12 месяцев (расчёт + короткие тексты, кеш на месяц)
   → Лира: долгосрочные периоды (готовые тексты планера,
   `build_planner(tier='pro')` longterm) → рендер → `commit_pdf` только
   при новой сборке → push «PDF готов» (docs/notifications.md).
   Детектор родовых форм (`interpretation/gender_check.py`) — по новым
   текстам. Beat: ежедневная чистка просроченных.
4. `natal_pdf.py`: разделы «Главные аспекты», «Главные транзиты: следующие
   6/12 месяцев», «Долгосрочные периоды»; бесплатный — как сейчас.
5. Веб: «Готовим PDF, это займёт до минуты» + прогресс (опрос статуса),
   список «PDF-отчёты» в карточке карты. Приложение — тот же список;
   скачивание — отдельная задача (плагин), согласовать с владельцем.
6. Каталог: строки `pdf` Веги/Лиры из task_current.md + `tierCatalog.test.js`.
7. Тест: PDF Веги и Лиры из фикстуры — разделы есть, нет английских
   названий и дат ГГГГ-ММ-ДД, «стр. N из M» верное.
8. `scripts/regen_interpretation_80605fbf.sh` — писать тариф; после деплоя
   дать владельцу команду.

Открытый вопрос к владельцу: скачивание PDF в приложении требует плагина
(Filesystem/Share) — делать в этом же разделе или отдельно (TASKS п. 2).

## Практические заметки

* Полный pytest локально не гонять; решающий — CI. Venv:
  `.venv/Scripts/python.exe`; скрипты с импортом `backend` — с
  `PYTHONPATH=.`.
* Heredoc через Bash ломает `\n` и `\.` в python-строках — правки regex и
  файлов с обратной косой — через Edit/Write.
* Порт 5199 обычно уже занят живым vite от прошлого захода — он и нужен.
