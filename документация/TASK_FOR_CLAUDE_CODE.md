# ТЗ: Расширение личного кабинета астролога — Astrea Timeline

> **Контекст проекта:** React 18 + React Router 6 + Vite 5 + Tailwind 3.4 (frontend), FastAPI + SQLAlchemy 2.0 + PostgreSQL (backend). Стек не менять. Все новые компоненты пишутся в том же стиле, что `CRMPage.jsx` — inline-стили через объект `S`, без CSS-файлов, без новых библиотек без согласования.

---

## Общие правила для всех задач

1. **Не трогай то, что не просили.** Если задача касается одного файла — меняй только его.
2. **Используй `authFetch` из `useAuth` для всех запросов к API.** Не используй `fetch` напрямую с ручным добавлением токена — исключение только там, где уже есть SSE-стримы (как в `loadAI` в `ClientCard`).
3. **Цветовая палитра проекта:** фон страницы `#0f172a`, карточки `#1e293b`, бордер `#334155`, текст `#e2e8f0`, мuted `#64748b`, accent `linear-gradient(135deg,#7C6CFF,#A78BFA)`.
4. **Все тексты интерфейса — на русском языке.**
5. **Не добавляй новые npm-пакеты без явного указания в задаче.**
6. **Новые эндпоинты backend пишутся в стиле существующих роутеров** (FastAPI, Pydantic-схемы, `get_current_user` через `Depends`).
7. **Миграции Alembic:** каждое новое поле/таблица — отдельная миграция, нумерация продолжается от `014_gift_codes` → следующая `015_...`.
8. **Не используй `alert()`.** Ошибки показывай через компонент `Toast` (уже существует) или строкой в интерфейсе как в `AddClientForm` (`setError`).

---

## Задача 1: Расписание и бронирование консультаций

### Цель
Астролог задаёт рабочие часы и длительность слота. Клиент открывает публичную ссылку и самостоятельно бронирует время. Астролог видит все брони в CRM.

### 1.1 Backend

**Новые таблицы (миграция `015_booking`):**

```sql
-- Таблица слотов астролога
CREATE TABLE booking_slots (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    day_of_week INTEGER NOT NULL,  -- 0=пн, 6=вс
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    slot_duration_minutes INTEGER NOT NULL DEFAULT 60,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Таблица бронирований
CREATE TABLE bookings (
    id SERIAL PRIMARY KEY,
    astrologer_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    client_profile_id INTEGER REFERENCES client_profiles(id) ON DELETE SET NULL,
    client_name VARCHAR(200) NOT NULL,
    client_email VARCHAR(200),
    client_phone VARCHAR(50),
    date DATE NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',  -- pending | confirmed | cancelled
    notes TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
```

**SQLAlchemy модели** — добавить в `models.py`.

**Новый роутер** `backend/booking/booking_router.py`:

```
POST   /api/v1/booking/slots            — сохранить расписание (список слотов, заменяет старые)
GET    /api/v1/booking/slots            — получить расписание текущего астролога
GET    /api/v1/booking/available/{date} — свободные слоты на дату (принимает ?astrologer_id=)
POST   /api/v1/booking/book             — забронировать слот (публичный, без авторизации)
GET    /api/v1/booking/bookings         — список бронирований астролога (с фильтром ?date=)
PATCH  /api/v1/booking/bookings/{id}    — изменить статус (confirmed/cancelled)
```

Правила:
- `POST /booking/book` — **публичный эндпоинт** (не требует JWT). Принимает `{astrologer_id, date, start_time, client_name, client_email, client_phone}`. Проверяет, что слот свободен (нет другого бронирования на это время у этого астролога со статусом не `cancelled`). Если занят — возвращает 409.
- `GET /booking/available/{date}` — тоже публичный. Возвращает список `[{start_time, end_time}]` свободных слотов на дату, исходя из расписания астролога и уже существующих бронирований.
- Все остальные эндпоинты — только для авторизованного Premium-пользователя.

**Зарегистрировать роутер** в `main.py` с префиксом `/api/v1/booking`.

### 1.2 Frontend

**Новый файл** `frontend/src/pages/BookingPublicPage.jsx`:
- Маршрут: `/book/:astrologerSlug` (slug = `astrologer_profiles.slug` или просто `user.id`)
- Показывает имя астролога, выбор даты (простой date input), список свободных слотов на выбранную дату (кнопки-чипы), форму с полями Имя / Email / Телефон.
- После успешного `POST /booking/book` показывает сообщение "Бронирование подтверждено".
- Стиль — тёмный, те же цвета проекта.

**Добавить в `App.jsx`** маршрут `<Route path="/book/:astrologerId" element={<BookingPublicPage />} />`.

**В `CRMPage.jsx`** — добавить новую вкладку в `ClientCard` под названием `📅 Записи`. Вкладка показывает список бронирований этого клиента (фильтр по `client_profile_id`). Каждая запись: дата, время, статус (цветной бейдж: pending=жёлтый, confirmed=зелёный, cancelled=серый), кнопки "Подтвердить" / "Отменить".

**В шапке CRM-страницы** (рядом с заголовком "Клиенты") добавить кнопку `📅 Моё расписание`. По клику открывается модальное окно (поверх контента, затемнённый backdrop) с формой настройки слотов:
- Для каждого дня недели (Пн–Вс) — чекбокс включить/выключить + поля "с" / "до" + "длительность слота (мин)".
- Кнопка "Сохранить расписание" вызывает `POST /api/v1/booking/slots`.
- Внизу модального окна — ссылка для клиента: `{APP_URL}/book/{user.id}` с кнопкой "Скопировать".

---

## Задача 2: Шаблоны заметок

### Цель
Астролог создаёт именованные шаблоны (например, "Первичная консультация", "Прогноз на год"). При открытии заметок для клиента — можно выбрать шаблон и вставить его текст как основу.

### 2.1 Backend

**Новая таблица (миграция `016_note_templates`):**

```sql
CREATE TABLE note_templates (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(200) NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
```

**Новый роутер** `backend/crm/note_templates_router.py`:
```
GET    /api/v1/note-templates           — список шаблонов текущего пользователя
POST   /api/v1/note-templates           — создать шаблон {title, content}
PATCH  /api/v1/note-templates/{id}      — обновить {title?, content?}
DELETE /api/v1/note-templates/{id}      — удалить
```

Все эндпоинты — только для авторизованного пользователя. При PATCH/DELETE проверять, что `template.user_id == current_user.id`, иначе 403.

**Зарегистрировать** в `main.py` с префиксом `/api/v1/note-templates`.

### 2.2 Frontend

**Изменения только в `CRMPage.jsx`**, вкладка `notes` в `ClientCard`:

Над textarea добавить:
1. Кнопку `📋 Шаблоны` — по клику открывается выпадающий список (dropdown, позиционированный absolute) с шаблонами пользователя. Клик на шаблон — вставляет его `content` в textarea (заменяет текущее содержимое, с confirm если textarea не пустой: "Заменить текущие заметки шаблоном?").
2. Кнопку `+ Новый шаблон` — открывает мини-форму прямо под кнопками: два поля (Название шаблона, Текст шаблона), кнопки "Сохранить шаблон" / "Отмена". После сохранения шаблон появляется в списке.

Шаблоны загружаются один раз при монтировании `ClientCard` через `GET /api/v1/note-templates`. Хранятся в state `ClientCard`.

**Не создавай отдельную страницу для управления шаблонами** — всё inline внутри вкладки заметок.

---

## Задача 3: История консультаций с таймлайном

### Цель
У каждого клиента в CRM — хронологическая лента событий: когда добавлен, когда были заметки, когда сгенерирован PDF-отчёт, когда забронирована консультация.

### 3.1 Backend

**Новая таблица (миграция `017_client_events`):**

```sql
CREATE TABLE client_events (
    id SERIAL PRIMARY KEY,
    client_profile_id INTEGER NOT NULL REFERENCES client_profiles(id) ON DELETE CASCADE,
    event_type VARCHAR(50) NOT NULL,
    -- Возможные значения:
    -- 'created'       — клиент добавлен
    -- 'notes_updated' — заметки сохранены
    -- 'report_pdf'    — PDF-отчёт сгенерирован
    -- 'booking'       — консультация забронирована/подтверждена
    -- 'manual'        — ручная запись астролога
    description TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
```

**Автоматическое создание событий:**
- При `POST /api/v1/clients` — создать событие `created` с description "Клиент добавлен".
- При `PATCH /api/v1/clients/{id}` (если изменились `notes`) — создать событие `notes_updated`.
- При `POST /api/v1/clients/{id}/report` — создать событие `report_pdf` с description "Сгенерирован PDF-отчёт".
- При `PATCH /api/v1/booking/bookings/{id}` (статус → `confirmed`) — создать событие `booking` с description "Консультация подтверждена: {дата} {время}".

**Новые эндпоинты** (добавить в `crm/crm_router.py`):
```
GET    /api/v1/clients/{id}/events      — список событий клиента (ORDER BY created_at DESC)
POST   /api/v1/clients/{id}/events      — добавить ручное событие {description}
```

### 3.2 Frontend

**Новая вкладка в `ClientCard`** — добавить `'timeline'` в массив `tabs` с лейблом `🕐 История`.

Вкладка рендерит вертикальный таймлайн:
- Каждое событие — строка с иконкой (🟢 created, 📝 notes_updated, 📄 report_pdf, 📅 booking, ✏️ manual), датой (формат `DD.MM.YYYY HH:MM`) и текстом события.
- Внизу таймлайна — форма добавления ручного события: одна строка textarea + кнопка "Добавить запись".
- Дата форматируется через `new Date(event.created_at).toLocaleString('ru-RU', {day:'2-digit', month:'2-digit', year:'numeric', hour:'2-digit', minute:'2-digit'})`.
- События загружаются при переключении на вкладку (не при монтировании).

---

## Задача 4: Библиотека сниппетов (готовые фразы)

### Цель
Астролог сохраняет часто используемые формулировки для отчётов. В PDF-отчёте может вставить их в нужные места. Минимальная версия: сниппеты доступны в интерфейсе заметок (как шаблоны, но отдельная коллекция отдельных фраз, а не целых документов).

### 4.1 Backend

**Новая таблица (миграция `018_snippets`):**

```sql
CREATE TABLE snippets (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    category VARCHAR(100),  -- например: "Солнце", "Луна", "Асцендент", "Прогнозы"
    title VARCHAR(200) NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
```

**Новый роутер** `backend/crm/snippets_router.py`:
```
GET    /api/v1/snippets                 — список (можно фильтр ?category=)
POST   /api/v1/snippets                 — создать {category?, title, content}
PATCH  /api/v1/snippets/{id}            — обновить
DELETE /api/v1/snippets/{id}            — удалить
GET    /api/v1/snippets/categories      — список уникальных категорий пользователя
```

Проверка `user_id` при PATCH/DELETE — аналогично шаблонам.

### 4.2 Frontend

**Новая страница** `frontend/src/pages/SnippetsPage.jsx`:
- Маршрут: `/dashboard/snippets`
- Добавить в навигацию (если есть сайдбар или меню) как `✍️ Сниппеты` — только для Premium.
- Макет: левая колонка — список категорий (кнопки-фильтры + "Все"), правая — список сниппетов с кнопками редактировать / удалить.
- Форма добавления сниппета: поля Категория (text input с datalist из существующих категорий), Название, Текст. Кнопка "Добавить".
- Редактирование inline (заменяет карточку сниппета на форму).

**В `ClientCard`, вкладка `notes`** — добавить вторую кнопку рядом с `📋 Шаблоны`: `✍️ Вставить сниппет`. Открывает dropdown с поиском по названию, клик вставляет `content` сниппета в textarea (в позицию курсора, не заменяя весь текст). Вставка в позицию курсора: `const pos = textareaRef.current.selectionStart; setNotes(prev => prev.slice(0, pos) + snippet.content + prev.slice(pos));`.

Для вставки в позицию курсора нужно добавить `ref={textareaRef}` к textarea (создать `const textareaRef = useRef(null)`).

---

## Задача 5: Конструктор брендирования PDF

### Цель
Вместо простого флага "брендирование включено" — полноценный редактор: загрузить логотип, выбрать акцентный цвет, ввести контактные данные. Превью показывает как будет выглядеть шапка отчёта.

### 5.1 Backend

**Изменить таблицу `astrologer_profiles`** (миграция `019_pdf_branding`), добавить поля:
```sql
ALTER TABLE astrologer_profiles ADD COLUMN IF NOT EXISTS brand_color VARCHAR(7) DEFAULT '#7C6CFF';
ALTER TABLE astrologer_profiles ADD COLUMN IF NOT EXISTS brand_logo_url TEXT;
ALTER TABLE astrologer_profiles ADD COLUMN IF NOT EXISTS contact_email VARCHAR(200);
ALTER TABLE astrologer_profiles ADD COLUMN IF NOT EXISTS contact_phone VARCHAR(50);
ALTER TABLE astrologer_profiles ADD COLUMN IF NOT EXISTS contact_website VARCHAR(200);
ALTER TABLE astrologer_profiles ADD COLUMN IF NOT EXISTS footer_text TEXT;
```

**Новый эндпоинт для загрузки логотипа** (добавить в существующий профильный роутер или в новый `branding_router.py`):
```
POST   /api/v1/branding/logo            — загрузить файл (multipart/form-data, поле 'file')
```
Сохранять файл в директорию `static/logos/` под именем `{user_id}.{ext}`. Возвращать `{logo_url: "/static/logos/{user_id}.{ext}"}`. Разрешённые форматы: jpg, jpeg, png, webp. Максимум 2MB (проверка по `file.size`). FastAPI монтирует `static/` через `app.mount("/static", StaticFiles(directory="static"), name="static")` — убедись, что это уже есть в `main.py`, иначе добавь.

**Обновить `natal_pdf.py`** — при генерации PDF для клиента (эндпоинт `POST /api/v1/clients/{id}/report`) подтягивать `astrologer_profiles` текущего пользователя и использовать:
- `brand_color` — цвет заголовков и разделителей в PDF.
- `brand_logo_url` — логотип в правом верхнем углу первой страницы (если задан, вставить через `reportlab.platypus.Image`).
- `contact_email`, `contact_phone`, `contact_website` — в футере каждой страницы.
- `footer_text` — подпись под контактами в футере.

### 5.2 Frontend

**В `ProfilePage.jsx`** или отдельном разделе настроек — добавить блок "Брендирование PDF" (только для Premium). Поля:
- Загрузить логотип: `<input type="file" accept="image/jpeg,image/png,image/webp" />`. После выбора файла — `POST /api/v1/branding/logo` с `FormData`. Показывать превью загруженного изображения.
- Акцентный цвет: `<input type="color" />` (стандартный color picker браузера, без библиотек).
- Email / Телефон / Сайт — обычные text input.
- Текст подписи (footer_text) — textarea.
- Кнопка "Сохранить" — `PATCH /api/v1/profile/astrologer` (или существующий эндпоинт обновления профиля).

**Блок превью** — статичный SVG или div, имитирующий шапку PDF: прямоугольник с выбранным цветом слева, место для логотипа справа, имя астролога. Обновляется по мере ввода (реактивно от state).

---

## Задача 6: Публичный профиль астролога

### Цель
Страница `astrea.app/astrologer/{id}` — публичная визитка астролога с описанием и кнопкой записи.

### 6.1 Backend

**Таблица `astrologer_profiles` уже существует.** Добавить недостающие поля (миграция `020_astrologer_public_profile`):
```sql
ALTER TABLE astrologer_profiles ADD COLUMN IF NOT EXISTS display_name VARCHAR(200);
ALTER TABLE astrologer_profiles ADD COLUMN IF NOT EXISTS bio TEXT;
ALTER TABLE astrologer_profiles ADD COLUMN IF NOT EXISTS specializations TEXT[];  -- массив строк
ALTER TABLE astrologer_profiles ADD COLUMN IF NOT EXISTS price_per_hour INTEGER;  -- в рублях
ALTER TABLE astrologer_profiles ADD COLUMN IF NOT EXISTS is_public BOOLEAN NOT NULL DEFAULT FALSE;
```

**Новый публичный эндпоинт** (добавить в существующий `profile` роутер или новый):
```
GET    /api/v1/public/astrologer/{user_id}   — публичная информация (только если is_public=true)
```
Возвращает: `{display_name, bio, specializations, price_per_hour, brand_color, brand_logo_url, contact_email, contact_website}`. Если `is_public=false` или профиль не найден — 404.

**Обновить эндпоинт профиля** (`PATCH /api/v1/profile/astrologer`) — добавить поддержку новых полей.

### 6.2 Frontend

**Новая страница** `frontend/src/pages/AstrologerPublicPage.jsx`:
- Маршрут: `/astrologer/:userId`
- Показывает: логотип/аватар, `display_name`, `bio`, список `specializations` (теги-чипы), цена за час, кнопка `📅 Записаться` — ведёт на `/book/{userId}`.
- Если 404 — "Профиль не найден или не опубликован".
- Стиль: тёмный фон, акцентный цвет из `brand_color` профиля используется для кнопки и разделителей.

**В `ProfilePage.jsx`** — добавить раздел "Мой публичный профиль" с полями: Отображаемое имя, О себе (textarea), Специализации (ввод тегами: input + Enter добавляет тег, крестик удаляет), Цена за час (number input), Переключатель "Профиль публичен" (toggle). После сохранения показывать ссылку на публичный профиль с кнопкой "Скопировать".

**Добавить маршрут** в `App.jsx`: `<Route path="/astrologer/:userId" element={<AstrologerPublicPage />} />`.

---

## Задача 7: Дашборд с аналитикой

### Цель
Отдельная вкладка/страница для астролога с ключевыми метриками по его базе клиентов.

### 7.1 Backend

**Новый эндпоинт** (добавить в `crm/crm_router.py`):
```
GET    /api/v1/clients/analytics        — агрегированная статистика
```

Возвращает JSON:
```json
{
  "total_clients": 42,
  "added_this_month": 5,
  "reports_generated": 18,
  "bookings_this_month": 8,
  "top_sun_signs": [
    {"sign": "Скорпион", "count": 7},
    {"sign": "Дева", "count": 5},
    ...
  ],
  "top_cities": [
    {"city": "Москва", "count": 12},
    ...
  ],
  "clients_by_month": [
    {"month": "2025-01", "count": 3},
    {"month": "2025-02", "count": 5},
    ...
  ]
}
```

`top_sun_signs` — из таблицы `natal_charts`, JOIN через `client_profiles.natal_chart_id`, брать поле с Солнцем (планета Sun, знак). Если планеты хранятся как JSON-массив — парсить на уровне Python. Возвращать топ-5.

`clients_by_month` — GROUP BY DATE_TRUNC('month', client_profiles.created_at), последние 6 месяцев.

`bookings_this_month` — COUNT из `bookings` WHERE `astrologer_id = current_user.id` AND `date >= начало текущего месяца`.

### 7.2 Frontend

**Новая страница** `frontend/src/pages/AnalyticsPage.jsx`:
- Маршрут: `/dashboard/analytics`
- Данные загружаются через `GET /api/v1/clients/analytics`.

**Макет — сетка карточек** (CSS Grid, 2 колонки на десктопе):

Карточка 1: "Всего клиентов" — большое число `total_clients`, под ним `+{added_this_month} в этом месяце`.

Карточка 2: "Отчётов создано" — число `reports_generated`.

Карточка 3: "Консультаций в этом месяце" — число `bookings_this_month`.

Карточка 4: "Топ знаков зодиака" — горизонтальные бары. Каждый бар — название знака + эмодзи (маппинг ниже) + число + полоска прогресса (div с background gradient, ширина = count/max*100%). **Не используй Chart.js или Recharts** — только CSS.

Маппинг знаков → эмодзи:
```js
const SIGN_EMOJI = {
  'Овен': '♈', 'Телец': '♉', 'Близнецы': '♊', 'Рак': '♋',
  'Лев': '♌', 'Дева': '♍', 'Весы': '♎', 'Скорпион': '♏',
  'Стрелец': '♐', 'Козерог': '♑', 'Водолей': '♒', 'Рыбы': '♓'
};
```

Карточка 5: "Рост базы клиентов" — простой спарклайн из `clients_by_month`. Реализовать как SVG-полилиния (без библиотек): нормализовать значения в диапазон высоты SVG, нарисовать `<polyline>` с акцентным цветом проекта. Под каждой точкой — метка месяца (сокращённо: Янв, Фев...).

Карточка 6: "Топ городов" — аналогичные горизонтальные бары как в карточке 4.

Добавить ссылку на аналитику в навигацию (только Premium): `📊 Аналитика`.

---

## Задача 8: Поиск паттернов по базе клиентов

### Цель
Астролог может фильтровать клиентов по астрологическим параметрам: знак Солнца, знак Луны, дом Асцендента и т.д.

### 8.1 Backend

**Новый эндпоинт** (добавить в `crm/crm_router.py`):
```
GET    /api/v1/clients/search
```

Query-параметры (все опциональные):
- `sun_sign` — строка, например "Скорпион"
- `moon_sign` — строка
- `asc_sign` — строка (знак Асцендента)
- `planet` — название планеты, например "Saturn"
- `house` — номер дома (1-12)
- `planet_in_house` — фильтр: планета `planet` в доме `house`

Логика:
- Загружать `client_profiles` с JOIN на `natal_charts` WHERE `client_profiles.user_id = current_user.id`.
- Планеты хранятся в `natal_charts.planets` как JSON. На Python-уровне парсить и фильтровать. Не пытаться делать сложный SQL по JSON — проще загрузить всё и отфильтровать в Python, клиентов у астролога обычно < 500.
- Возвращать тот же формат что `GET /api/v1/clients` — список клиентов.

**Важно:** маршрут `/clients/search` должен быть зарегистрирован **до** маршрута `/clients/{id}` в роутере, иначе FastAPI будет пытаться интерпретировать "search" как `id` и вернёт 422/404.

### 8.2 Frontend

**Изменения только в `CRMPage.jsx`** компонент `ClientList`:

Добавить кнопку `🔍 Фильтр по карте` рядом со строкой поиска. По клику раскрывается панель фильтров (toggle, не модальное окно):

```
[Знак Солнца ▾] [Знак Луны ▾] [Знак Асцендента ▾] [Планета ▾] в [Доме ▾] [Применить] [Сбросить]
```

Все выпадающие — `<select>` со стилями из `S.input`. Первая опция каждого select — "Любой" (value="").

Список знаков зодиака (константа вверху файла):
```js
const ZODIAC_SIGNS = ['Овен','Телец','Близнецы','Рак','Лев','Дева','Весы','Скорпион','Стрелец','Козерог','Водолей','Рыбы'];
```

Список планет:
```js
const PLANETS = ['Sun','Moon','Mercury','Venus','Mars','Jupiter','Saturn','Uranus','Neptune','Pluto'];
```

Список домов: 1–12.

Поведение кнопки "Применить":
- Если все фильтры пустые — загружать обычный `GET /api/v1/clients`.
- Если есть хоть один фильтр — `GET /api/v1/clients/search?sun_sign=...&...`, игнорировать пустые параметры.
- Результат заменяет текущий `clients` в state на время поиска. При сбросе — вернуть оригинальный список.

Кнопка "Сбросить" — очищает все фильтры, скрывает панель, возвращает полный список.

Если поиск вернул 0 клиентов — показать: "По заданным параметрам клиентов не найдено."

---

## Порядок выполнения (рекомендуемый)

1. Задача 3 (таймлайн) — самая простая backend часть, хорошо для разогрева.
2. Задача 2 (шаблоны заметок) — изолированная, не зависит от других.
3. Задача 4 (сниппеты) — похожа на задачу 2, быстро.
4. Задача 8 (поиск паттернов) — frontend-изменения минимальны.
5. Задача 7 (аналитика) — нужна после задачи 1 (бронирования) для полноты данных, но можно без них.
6. Задача 1 (расписание) — самая объёмная, делать последней или отдельно.
7. Задача 5 (брендирование PDF) — требует работы с файлами, тестировать отдельно.
8. Задача 6 (публичный профиль) — зависит от задачи 5 (brand_color, logo_url).

---

## Чек-лист перед завершением каждой задачи

- [ ] Миграция Alembic создана и применена (`alembic upgrade head`).
- [ ] Pydantic-схемы для всех новых эндпоинтов написаны в `schemas.py`.
- [ ] Новый роутер подключён в `main.py`.
- [ ] Публичные эндпоинты не требуют авторизации (нет `Depends(get_current_user)`).
- [ ] Закрытые эндпоинты проверяют `user_id` для защиты от доступа к чужим данным.
- [ ] Frontend: нет прямых вызовов `fetch` с ручным токеном (кроме SSE-стримов).
- [ ] Frontend: нет `alert()`.
- [ ] Frontend: все стили через объект `S` или inline, без новых CSS-файлов.
- [ ] Новые маршруты добавлены в `App.jsx`.
