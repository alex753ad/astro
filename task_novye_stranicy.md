# Задание для Claude Code: Соляр, Синастрия, Релокация

Проект: `https://github.com/alex753ad/astro.git`
Сначала прочитай `CLAUDE.md` и следуй его правилам.

**Работай полностью автономно: не задавай уточняющих вопросов, не жди
подтверждений. Все технические развилки решай сам по фактической структуре
кода. Если встречается неоднозначность — выбирай наиболее очевидный вариант,
фиксируй выбор комментарием в коде и продолжай. Останавливайся и спрашивай
ТОЛЬКО если продолжение физически невозможно (например, нет доступа к нужному
файлу). После каждой логической части прогоняй тесты и иди дальше без паузы.
Итоговый отчёт — в самом конце.**

**Это техническое задание описывает намерение и даёт технические ориентиры
(конкретные функции/файлы для переиспользования). Если по ходу работы
выяснится, что что-то в проекте устроено иначе или есть более подходящий
способ реализации — делай по своему усмотрению, ориентируясь на факт��ческую
структуру кода, а не на это задание дословно.**

**Доступ — ТОЛЬКО для администраторов (`is_admin = true`).** Никакого
paywall/тиров тут нет — вместо этого весь функционал закрыт админ-проверкой
(см. раздел «Доступ» ниже). Выбор модели AI (GPT-4o / DeepSeek) и объём текста
по-прежнему определяются тиром пользователя так же, как для существующей
натальной интерпретации (см. `select_model()` в
`backend/interpretation/router.py`) — но доступ к самим страницам есть только
у админа.

---

## Доступ: только админ (обязательно на обоих уровнях)

Проверка тарифа не нужна — вместо неё везде админ-гейт. Флаг `is_admin` уже
есть в модели `User` и отдаётся в `/auth/me`. Зависимость для проверки —
`require_admin` в `backend/admin/` (используется существующими admin-роутами;
найди её и переиспользуй, не пиши новую).

**Бэкенд — все 6 новых эндпоинтов:**
- POST-эндпоинты (`/solar-return`, `/synastry`, `/synastry/interpret`,
  `/relocation`) — добавить `Depends(require_admin)`; не-админ получает **403**.
- SSE-GET эндпоинты (`/solar-return/{year}/interpret`,
  `/relocation/interpret`) — аутентификация идёт через тикет; после резолва
  пользователя явно проверить `user.is_admin`, иначе **403**. Проверку сделать
  и на выдаче тикета, если это возможно в текущей схеме `sse_tickets.py`.

**Фронтенд:**
- Роуты `/solar-return/:chartId`, `/synastry/:chartId`, `/relocation/:chartId`
  обернуть в admin-guard: если `user` не админ — редирект на главную (или на
  страницу натальной карты). Посмотри, есть ли в проекте уже готовый
  `ProtectedRoute`/guard, и переиспользуй его; если нет — простая проверка
  `user?.is_admin` внутри страницы с `<Navigate>`.
- Дропдаун «Расчёты ▾» и мобильные ссылки показывать **только** при
  `user?.is_admin` (в дополнение к условию `lastChartId`).

---

## 0. Важные технические находки (проверено в коде)

- `calculate_aspects()` в `backend/ephemeris/aspects.py` считает аспекты
  **внутри одного списка планет** (комбинации первой карты с самой собой).
  Для межкарточных аспектов синастрии это **не подходит напрямую** —
  нужна отдельная функция, сравнивающая планеты карты 1 с планетами карты 2
  попарно. Ориентируйся на структуру `AspectResult` / `ASPECTS` /
  `DEFAULT_ORBS` в том же файле, но пиши отдельную функцию
  (например `calculate_synastry_aspects(planets1, planets2)`).

- Для точного момента соляра (когда транзитный Солнце возвращается на
  натальную долготу Солнца) в проекте уже есть механизм тернарного
  поиска + бисекции по юлианским дням: `_find_exact_aspect()` в
  `backend/transit/engine.py`. Это ближайший референс — адаптируй его
  логику (target_angle=0, transit_planet=Sun, natal_longitude=натальное
  Солнце), только окно поиска — не часы, а весь указанный год.
  Простая идея "рассчитать карту на 1 июня года X" даст **неточный** соляр —
  так делать не надо.

- В `NatalChart` (модель `backend/models.py`) уже хранятся
  `utc_datetime`, `latitude`, `longitude`, `timezone` — для релокации и
  соляра не нужно пересчитывать натальные данные заново, только доставать
  их из сохранённой карты по `chart_id`.

- AI-интерпретация в проекте всегда идёт через `InterpretationRequest`
  (`backend/interpretation/base.py`). У неё уже есть поле `custom_prompt` —
  если оно задано, движки (`gpt4o.py`, судя по всему и `deepseek.py`)
  используют его напрямую вместо стандартного `build_system_prompt()`.
  Это и есть штатный механизм для новых типов интерпретации — **не нужно
  трогать `build_system_prompt()`**, вместо этого пиши отдельные функции
  построения промпта по образцу `backend/transit/prompts.py`
  (`build_transit_period_prompt`, `build_transit_event_prompt`).
  Аналогично сделай `build_solar_return_prompt`, `build_synastry_prompt`,
  `build_relocation_prompt`.

- Стриминг для интерпретации с телом запроса (POST, не GET+EventSource)
  уже реализован для `/chart/{id}/transits/event/interpret` в
  `backend/main.py` (~строка 1125) — это лучший референс для новых
  эндпоинтов интерпретации соляра/синастрии/релокации, т.к. им тоже нужно
  передавать данные в body (год, вторая карта, город), а не только query.
  На фронтенде соответствующий паттерн — `streamTransitEventInterpretation`
  в `frontend/src/api/client.js` (fetch + ReadableStream, парсинг `data: `
  строк), а не `EventSource`.

- В `InterpretationRouter._validate_response()` (`backend/interpretation/
  router.py`) есть спец-случай: `if context == "transit": return True`
  (валидация по натальным ключевым словам пропускается). Для новых
  контекстов (`solar_return`, `synastry`, `relocation`) нужно либо
  добавить их в этот же обход, либо обобщить условие — иначе валидатор
  может забраковать корректный ответ, ищущий слова "карьера"/"отношения".

---

## 1. Backend — 3 новых эндпоинта расчёта + 3 эндпоинта интерпретации

### 1.1 Соляр

**POST `/api/v1/chart/{chart_id}/solar-return`**
- Body: `{ "year": 2026, "location": "Москва, Россия" }` (location опционален —
  если не передан, берётся `birth_place`/координаты натальной карты)
- Достать натальную карту по `chart_id` (переиспользуй существующую функцию
  доступа к карте — в `main.py` уже есть `resolve_chart_access()`, используй
  её вместо ручной проверки владельца)
- Найти точный момент возврата Солнца в указанном году (см. раздел 0)
- Геокодинг локации через `backend/ephemeris/geo.py::geocode_place()`,
  если location передан; иначе — координаты натальной карты
- Рассчитать карту на найденный момент через `calculate_full_chart()`
  (`backend/ephemeris/calculator.py`)
- Ответ: тот же формат, что у `/chart/calculate` (`NatalChartResponse` из
  `backend/schemas.py`), плюс поле `solar_return_datetime` (UTC момент точного соляра)

**GET `/api/v1/chart/{chart_id}/solar-return/{year}/interpret`** (SSE)
- Query: `location` опционально
- Собрать профиль соляра (как выше), построить промпт через
  `build_solar_return_prompt()`, передать как `custom_prompt` в
  `InterpretationRequest(context="solar_return", ...)`
- Стримить по образцу существующего SSE-эндпоинта натальной интерпретации
  (`/chart/{chart_id}/interpret`, ~строка 681 в `main.py`) — включая
  использование тикетов (`backend/auth/sse_tickets.py`), т.к. это GET

### 1.2 Синастрия

**POST `/api/v1/chart/synastry`**
- Body: `{ "chart_id": "...", "partner": { name, birth_date, birth_time, birth_place, house_system } }`
  — первая карта берётся из БД по `chart_id`, вторая считается на лету из
  `partner` (не сохраняется в БД)
- Рассчитать вторую карту через `calculate_full_chart()` (с геокодингом
  `partner.birth_place` через `geocode_place()` и резолвом времени через
  `resolve_utc_datetime()` из `geo.py`)
- Посчитать межаспектную сетку новой функцией (см. раздел 0)
- Ответ: `{ chart1: {...}, chart2: {...}, cross_aspects: [...] }`

**POST `/api/v1/chart/synastry/interpret`** (SSE, POST — по образцу
`transits/event/interpret`)
- Body: тот же, что у расчёта синастрии
- Построить промпт через `build_synastry_prompt()`, передать как
  `custom_prompt`, `context="synastry"` (это значение уже присутствует как
  допустимое в `InterpretationRequest.context` — используй его)

### 1.3 Релокация

**POST `/api/v1/chart/{chart_id}/relocation`**
- Body: `{ "location": "Барселона, Испания" }`
- Достать `utc_datetime` натальной карты по `chart_id` (уже хранится,
  пересчитывать дату/время не нужно)
- Геокодировать новую локацию, пересчитать `calculate_full_chart()` с
  теми же `utc_datetime`, но новыми координатами и той же `house_system`
- Ответ: `NatalChartResponse` + поле `relocated_location`

**GET `/api/v1/chart/{chart_id}/relocation/interpret`** (SSE)
- Query: `location`
- `build_relocation_prompt()`, `context="relocation"`, стриминг по образцу
  натального SSE-эндпоинта (тикеты)

---

## 2. Frontend — 3 новые страницы

**Общие требования:**
- Стилизация через CSS-переменные (`var(--accent)`, `var(--bg-card)`,
  `var(--border)`, `var(--text-primary)`, `var(--text-secondary)`) — как в
  `BirthForm.jsx` и `ChartPage.jsx`
- Кнопки — `MotionButton` (`./components/MotionButton`)
- Поля ввода города/даты — скопируй `PlaceInput`, `DateMaskInput`,
  `StyledInput`, `Field` прямо из `BirthForm.jsx` в новую страницу (не
  выносить в общий компонент, если явно не попросят)
- Показ результата расчёта — переиспользуй `NatalChart` (SVG-колесо) и
  `AspectTable`/`AspectTableWrapper` из `components/`, как это сделано в
  `ChartPage.jsx`
- Показ AI-интерпретации — переиспользуй компонент `Interpretation.jsx`
  (проверь его пропсы — он уже умеет работать со стримом секций
  `<section name="...">`) либо адаптируй по аналогии
- Никаких проверок тарифа/paywall — вместо этого admin-гейт (см. раздел «Доступ»)
- Layout: `max-w-2xl mx-auto px-4 py-8` (шире — до `max-w-4xl`, если на
  странице два колеса рядом, как в синастрии)

### `frontend/src/pages/SolarReturnPage.jsx` — route `/solar-return/:chartId`
- Выбор года (select, текущий год ± 5 лет)
- Опционально — другой город (PlaceInput, плейсхолдер "по умолчанию — место рождения")
- Кнопка "Рассчитать соляр" → показать `NatalChart` + таблицу планет/аспектов
- Кнопка/автозапуск "Получить интерпретацию" → стрим через POST fetch-паттерн
  (или GET+ticket, в зависимости от того, как реализован бэкенд-эндпоинт)

### `frontend/src/pages/SynastryPage.jsx` — route `/synastry/:chartId`
- Форма партнёра: имя, дата рождения (`DateMaskInput`), время
  (`StyledInput type="time"` + чекбокс "не знаю точное время"), город
  (`PlaceInput`)
- После расчёта: два `NatalChart` рядом (или один совмещённый — на
  усмотрение реализации) + таблица `cross_aspects` (планета1 × планета2 ×
  тип аспекта × орб)
- Кнопка интерпретации — стрим совместимости

### `frontend/src/pages/RelocationPage.jsx` — route `/relocation/:chartId`
- Поле "Новый город" (`PlaceInput`)
- Подпись: "Дата и время рождения остаются прежними — меняются только
  координаты"
- После расчёта: `NatalChart` с релокационными данными + сравнение домов
  в две колонки ("Натальные дома" / "Дома в релокации" — оба списка можно
  получить одним ответом или дополнительным вызовом `/chart/{id}` для
  исходных домов)
- Кнопка интерпретации

---

## 3. `frontend/src/api/client.js` — новые функции

```js
export async function calculateSolarReturn(chartId, year, location = null) { ... }
export async function streamSolarReturnInterpretation(chartId, year, location, onChunk, onDone, onError) { ... }

export async function calculateSynastry(chartId, partnerData) { ... }
export async function streamSynastryInterpretation(chartId, partnerData, onChunk, onDone, onError) { ... }

export async function calculateRelocation(chartId, location) { ... }
export async function streamRelocationInterpretation(chartId, location, onChunk, onDone, onError) { ... }
```

Для расчётов (POST без стрима) — обычный `request()`, как существующие
функции. Для стримов — по тому, GET это или POST на бэкенде:
GET+ticket → паттерн `streamInterpretation`/`_connectSSE`; POST-стрим →
паттерн `streamTransitEventInterpretation` (fetch + ReadableStream).

---

## 4. `frontend/src/App.jsx` — роуты и навигация

**Роуты:**
```jsx
<Route path="/solar-return/:chartId" element={<SolarReturnPage />} />
<Route path="/synastry/:chartId"     element={<SynastryPage />} />
<Route path="/relocation/:chartId"   element={<RelocationPage />} />
```

**Навигация в `Header`** — выпадающее меню "Расчёты ▾" рядом с
существующими пунктами, только при `user?.is_admin && lastChartId`:
```
Расчёты ▾
  ├── Соляр       → /solar-return/{lastChartId}
  ├── Синастрия   → /synastry/{lastChartId}
  └── Релокация   → /relocation/{lastChartId}
```
Стиль дропдауна — как у существующих `navLink` (border, bg-card,
backdrop-blur). В мобильном меню — три плоские ссылки без дропдауна,
рядом с уже существующими пунктами мобильного меню.

---

## Что НЕ делать
- Не трогать существующие страницы, компоненты, эндпоинты
- Не добавлять новые npm/pip зависимости
- Не сохранять результаты соляра/синастрии/релокации в БД — только
  возвращать напрямую (без миграций Alembic)
- Не переиспользовать `BirthForm.jsx` целиком на новых страницах —
  копировать только нужные подкомпоненты
- Не менять `build_system_prompt()` в `backend/interpretation/prompts.py` —
  для новых расчётов промпты строятся отдельными функциями и передаются
  через `custom_prompt`
