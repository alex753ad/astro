# Разведка боевых ручек под экран «Ещё»

Снято 06.09.2026 с прода (`https://aristeatime.ru/api/v1`) под служебным
аккаунтом (`TEST_ACCOUNT_EMAIL` / `TEST_ACCOUNT_PASSWORD` из корневого
`.env`, тариф **free**). Всё ниже — фактические ответы сервера, не
пересказ схем и не чтение кода. Где утверждение выведено из кода, это
сказано явно.

Аналог `CHART_API_RECON.md`, тот же принцип: сначала что реально
приходит, потом чего не хватает для прототипа.

## Условия прогона

- Запросы — прямым HTTPS (`urllib`), без браузера: CORS прода не пускает
  dev-origin, но это ограничение браузера, а не API.
- Все ручки без токена отвечают **401** (проверено на `/auth/me`,
  `/profile/charts`, `/profile/subscription`, `/profile/referral`).
- Токен — обычный access из `POST /auth/login`, живёт 900 секунд
  (`expires_in`).

---

# 1. Ручка под каждый блок экрана

Прототип (`aristea-mobile.html`, ЭКРАН 3) требует шесть блоков. Ручка
нашлась для **всех шести** — заглушек по причине «нет API» на этом
экране не будет.

| Блок прототипа | Метод и путь | Авторизация | Гейт по тарифу |
|---|---|---|---|
| Шапка: имя + почта | `GET /api/v1/auth/me` | обязательна | **нет** |
| Блок тарифа | `GET /api/v1/profile/subscription` | обязательна | **нет** |
| «Мои карты» | `GET /api/v1/profile/charts` | обязательна | **нет** |
| История разборов | `GET /api/v1/profile/history` | обязательна | **нет** |
| Друзья | `GET /api/v1/profile/referral` | обязательна | **нет** |
| Уведомления | `GET`/`PATCH /api/v1/push/settings` | обязательна | **нет** |
| Скачать мои данные | `GET /api/v1/profile/export` | обязательна | **нет**, но rate limit `3/hour` |
| Настройки | `GET`/`PATCH /api/v1/profile/settings` | обязательна | **нет** |

**Ни одна ручка этого экрана не гейтится тарифом.** Единственное
ограничение во всём наборе — `@limiter.limit("3/hour", key_func=export_key)`
на выгрузке (`profile/router.py:379`). Проверено по коду: в
`backend/profile/router.py` и `backend/push/router.py` нет ни одного
`require_*`, ни одной проверки `tier` перед выдачей данных.

Сопутствующие ручки того же экрана (нужны для действий, не для показа):

```
PATCH  /api/v1/profile/primary-chart     — сделать карту основной
PATCH  /api/v1/profile/name              — переименовать пользователя
DELETE /api/v1/profile/charts/{chart_id} — удалить карту
DELETE /api/v1/profile/data              — удалить все данные
DELETE /api/v1/auth/me                   — удалить аккаунт
GET    /api/v1/push/vapid-public-key
POST   /api/v1/push/subscribe
POST   /api/v1/push/unsubscribe
POST   /api/v1/push/test
```

Grep делался по URL-путям во всём `frontend/src`, а не по именам обёрток
из `api/client.js` — иначе половина этих путей не нашлась бы. Так,
`/profile/settings` зовётся напрямую из `hooks/useExpertMode.js`, а
`/push/*` — из `push.js` и `ProfilePage.jsx`, мимо `client.js`.

---

# 2. Полные боевые ответы

## `GET /auth/me` — шапка экрана целиком

```json
{
  "id": "1bcbb20b-6ff2-4dc1-bd51-b5cecc034e18",
  "email": "aristeatime@mail.ru",
  "name": "aristea",
  "tier": "free",
  "is_email_confirmed": true,
  "is_admin": false,
  "is_partner": false,
  "stripe_customer_id": null,
  "created_at": "2026-09-04T12:11:07.441843"
}
```

Это главная ручка экрана: **имя, почта и тариф приходят одним запросом**.
`POST /auth/login` отдаёт ровно те же поля (`name`, `email`, `tier`,
`user_id`, `is_admin`, `is_partner`) плюс токены, но на login полагаться
нельзя: при холодном старте приложения в `localStorage` есть токен, а
ответа логина уже нет.

⚠️ `stripe_customer_id` — **мёртвое поле**. Stripe удалён из проекта
19.08.2026 (см. CLAUDE.md), а поле в ответе осталось и всегда `null`. Не
использовать и не считать признаком чего-либо.

## `GET /profile/subscription` — блок тарифа

```json
{
  "tier": "free",
  "is_active": false,
  "stripe_subscription_id": null,
  "stripe_customer_id": null,
  "status": "free",
  "current_period_end": null,
  "features": {
    "tier": "free",
    "interpretation_word_limit": 500,
    "interpretations_per_month": 0,
    "first_interpretation_free": true,
    "charts_per_day": null,
    "transits_months": 0,
    "transits_ai": false,
    "transits_ai_per_month": 0,
    "profiles_limit": 2,
    "lunar_months": 1,
    "planner_months": 0,
    "synastry": false,
    "pdf_export": true,
    "pdf_per_month": 1,
    "ai_engine": "deepseek-v4-pro",
    "transits": false,
    "transits_ai_limited": false,
    "first_interpretation_available": false,
    "unlimited_interpretations": false,
    "unlimited_charts": false,
    "pdf_reports": true,
    "google_calendar": false,
    "rag_chat": false,
    "crm": false
  },
  "limits": {
    "interpretation_word_limit": 500,
    "interpretations_per_month": 0,
    "first_interpretation_free": true,
    "charts_per_day": null,
    "transits_months": 0,
    "transits_ai": false,
    "transits_ai_per_month": 0,
    "profiles_limit": 2,
    "lunar_months": 1,
    "planner_months": 0,
    "synastry": false,
    "pdf_export": true,
    "pdf_per_month": 1,
    "ai_engine": "deepseek-v4-pro"
  },
  "usage": {
    "ai_interpretations_this_month": 0,
    "transit_ai_this_month": 0,
    "pdf_this_month": 0,
    "charts_this_month": 2
  }
}
```

`features` и `limits` — почти одно и то же: `limits` это сырой
`get_tier_limits(tier)`, а `features` — он же плюс девять производных
булевых (`transits`, `pdf_reports`, `rag_chat`, `crm`,
`first_interpretation_available` и т.д.). Дублирование в ответе есть,
это не ошибка снятия.

## `GET /profile/charts` — «Мои карты»

```json
{
  "total": 2,
  "offset": 0,
  "limit": 20,
  "primary_chart_id": null,
  "charts": [
    {
      "id": "b1ae94f2-d64f-4f31-81e2-8555ca8a1e37",
      "birth_date": "1990-06-15",
      "birth_time": "14:30",
      "birth_place": "Москва, Центральный федеральный округ, Россия",
      "house_system": "placidus",
      "time_unknown": false,
      "created_at": "2026-09-04T14:43:42.059052",
      "is_primary": false
    },
    {
      "id": "5b86294d-74c6-4ae6-b722-b375793323ee",
      "birth_date": "1996-05-28",
      "birth_time": "11:50",
      "birth_place": "Москва, Центральный федеральный округ, Россия",
      "house_system": "placidus",
      "time_unknown": false,
      "created_at": "2026-09-04T13:02:32.229617",
      "is_primary": false
    }
  ]
}
```

- Карт **две** (`total: 2`), при `profiles_limit: 2` — слоты заняты
  полностью.
- Метка основной карты **есть как механизм**: `primary_chart_id` в корне
  и `is_primary` у каждой. Но у служебного аккаунта она **не выставлена**
  — `primary_chart_id: null`, обе карты `is_primary: false`. То есть
  состояние «основная не выбрана» — реальное и на экране встретится.
- **Имени карты в ответе нет вообще.** Ни `name`, ни `label` — см. §3.
- Порядок — `created_at DESC` (свежая первой), задан в запросе
  (`profile/router.py:53`).
- Пагинация есть: `limit` по умолчанию 20, максимум 100.

## `GET /profile/history` — история разборов

```json
{
  "total": 1,
  "offset": 0,
  "limit": 20,
  "history": [
    {
      "id": "a63e96f8-4a2b-4fd5-a836-dcfff32dd7a1",
      "chart_id": "b1ae94f2-d64f-4f31-81e2-8555ca8a1e37",
      "engine": "deepseek",
      "created_at": "2026-09-05T20:57:30.359983",
      "preview": "<section name=\"general\">\nТы человек, в котором уживаются две сильные тяги: одна — к ясности, словам, смыслу, другая — к глубине, чувству и тишине. Солнце и Меркурий в Близнецах в девятом доме дают жив"
    }
  ]
}
```

Что здесь важно для экрана:

- Запись **одна** — ровно та единственная бесплатная интерпретация
  (`first_interpretation_free: true`, а `first_interpretation_available`
  уже `false`: израсходована).
- `preview` — **сырой обрезок текста с неразобранной разметкой**:
  начинается с `<section name="general">` и обрывается на полуслове.
  Тег в превью придётся резать на клиенте, иначе он попадёт в список
  как видимый текст.
- Названия разбора в записи **нет** — только `chart_id`. Чтобы подписать
  строку истории («разбор карты такой-то»), придётся сопоставлять
  `chart_id` со списком карт, а у карт нет имени (§3) — значит подпись
  может быть только по дате рождения и месту.
- `engine: "deepseek"` — совпадает с единым движком из CLAUDE.md.

## `GET /profile/referral` — «Друзья»

```json
{
  "ref_code": "VKKC1END",
  "ref_url": "https://www.aristeatime.ru?ref=VKKC1END",
  "referrals_count": 0,
  "reward_weeks_earned": 0
}
```

## `GET /profile/settings` — «Настройки»

```json
{
  "expert_mode": false,
  "digest_day_of_week": 0
}
```

Всего два поля. `PATCH` принимает `expert_mode` и `digest_day` (0=пн … 6=вс).

## `GET /push/settings` — «Уведомления»

```json
{
  "daily_forecast": true,
  "daily_time": "08:00",
  "planner": true,
  "key_transits": true,
  "moon_phases": false
}
```

`GET /push/vapid-public-key` отвечает 200 и отдаёт ключ:

```json
{"public_key": "BL4-IonwT4WPfyzEU-dfVPU80IK_BS8rhNGAs_HgZ3ixmEcpoZq7VRkjjYVtrnZrW8Xvwy7btIiRggEm1tatmUM"}
```

## `GET /profile/export` — «Скачать мои данные»

Отдаёт **JSON-объект в теле ответа**, а не файл: 8763 байта, семь ключей
верхнего уровня. Ниже полный ответ, у интерпретации обрезано только поле
`content` (там ~8 КБ связного текста):

```json
{
  "exported_at": "2026-09-06T15:16:19.507782",
  "account": {
    "email": "aristeatime@mail.ru",
    "name": "aristea",
    "tier": "free",
    "is_email_confirmed": true,
    "created_at": "2026-09-04T12:11:07.441843"
  },
  "consent": {
    "given_at": "2026-09-04T12:11:07.437195",
    "terms_version": "2026-09-02",
    "privacy_version": "2026-09-02"
  },
  "charts": [
    {
      "id": "5b86294d-74c6-4ae6-b722-b375793323ee",
      "label": null,
      "name": null,
      "birth_date": "1996-05-28",
      "birth_time": "11:50",
      "birth_place": "Москва, Центральный федеральный округ, Россия",
      "latitude": 55.625578,
      "longitude": 37.606392,
      "timezone": "Europe/Moscow",
      "time_unknown": false,
      "house_system": "placidus",
      "created_at": "2026-09-04T13:02:32.229617"
    },
    {
      "id": "b1ae94f2-d64f-4f31-81e2-8555ca8a1e37",
      "label": null,
      "name": null,
      "birth_date": "1990-06-15",
      "birth_time": "14:30",
      "birth_place": "Москва, Центральный федеральный округ, Россия",
      "latitude": 55.625578,
      "longitude": 37.606392,
      "timezone": "Europe/Moscow",
      "time_unknown": false,
      "house_system": "placidus",
      "created_at": "2026-09-04T14:43:42.059052"
    }
  ],
  "interpretations": [
    {
      "id": "a63e96f8-4a2b-4fd5-a836-dcfff32dd7a1",
      "chart_id": "b1ae94f2-d64f-4f31-81e2-8555ca8a1e37",
      "engine": "deepseek",
      "content": "<section name=\"general\">\nТы человек, в котором уживаются две сильные тяги… [обрезано, ~8 КБ]",
      "created_at": "2026-09-05T20:57:30.359983"
    }
  ],
  "payments": [],
  "aristea_chat_summary": null
}
```

⚠️ Выгрузка отдаёт **координаты рождения** (`latitude`/`longitude`) и
полный текст интерпретаций. Если экран будет что-то из неё показывать —
это те же персональные данные, что и в карте.

---

# 3. Чего нет

Ручки есть под все пункты меню. Не хватает **данных внутри них**, и одна
нехватка определяет вид экрана.

## ⚠️ Имени карты не существует — ни у кого, а не только здесь

`GET /profile/charts` не отдаёт `name`/`label`. Это не особенность
служебного аккаунта: проверено по коду, а не по одному ответу.

1. Колонки в модели есть — `models.py:108-109` (`label`, `name`,
   оба `nullable=True`).
2. `list_charts` собирает словарь ответа **вручную** и просто не кладёт
   туда эти два поля (`profile/router.py:59-71`).
3. `BirthDataInput` **принимает** `name` (`schemas.py:17`) — и его
   действительно можно прислать.
4. Но при создании записи `NatalChart(...)` поле `name` **не
   передаётся**: ни в `POST /chart/calculate` (`main.py:692-708`), ни в
   `POST /chart/save-anonymous` (`main.py:892-908`).
5. Grep по всему `backend/` не нашёл **ни одного** места, где
   `NatalChart.name` или `.label` присваивается. CRM тоже не пишет.

**Итог: присланное клиентом имя карты молча выбрасывается, колонка всегда
`NULL`.** В выгрузке `/profile/export` поля видны — и там они `null` у
обеих карт, что это и подтверждает.

Практическое следствие для экрана: строка «Мои карты» в прототипе
(`<b>Александр</b>` / `<b>Мария</b>`) **нечем заполнить**. Различать
карты можно только датой рождения и местом — а у служебного аккаунта
место у обеих одинаковое («Москва…»), то есть отличаются они по факту
одной датой.

## Дата окончания подписки: поле есть, значения на free нет

`current_period_end` в `/profile/subscription` присутствует, но `null`.
Для free это не пропуск данных, а верное состояние: подписки нет,
`is_active: false`, `status: "free"`. Проверить непустое значение этим
аккаунтом невозможно — нужен платный. Из кода
(`profile/router.py:313-316`) видно, что значение берётся из записи
подписки, если она есть.

## Отдельной ручки «остаток лимитов» нет

Готового «осталось N разборов» сервер не отдаёт. Есть две половины в
одном ответе `/profile/subscription`, вычитать их надо на клиенте:
`limits.interpretations_per_month` (сколько положено) минус
`usage.ai_interpretations_this_month` (сколько потрачено). То же для
`pdf_per_month` / `pdf_this_month` и `transits_ai_per_month` /
`transit_ai_this_month`.

Для free это вырожденный случай: `interpretations_per_month: 0` при
`first_interpretation_free: true` — квоты нет вовсе, а есть одна
бесплатная навсегда, и её остаток лежит в **отдельном** флаге
`features.first_interpretation_available` (здесь уже `false`).
Арифметика «лимит минус расход» этот случай не описывает.

## `TIER_ORDER` из `constants.js` не экспортируется

В задании он назван источником, но в `constants.js` его **нет** — только
упоминание в комментарии первой строки. Экспортируются оттуда:
`TIER_NAMES`, `TIER_NAMES_GENITIVE`, `TIER_PRICES`, `tierPriceLabel`,
`TIER_PDF_PER_MONTH`, `pdfFeatureLabel`, `TIERS`, `tierFeatures`,
`FREE_TRANSITS_TEASER_MONTHS`.

Сам порядок живёт тремя независимыми копиями:
`ProfilePage.jsx:499`, `backend/feed/horizon.py:42`,
`test_rate_limits.py:294`. Четвёртую копию в мобильном заводить — тот же
класс дефекта, что уже описан в CLAUDE.md про `charts_per_month`.

**Но следующий тариф уже приходит с сервера** — в ответе ленты
`GET /chart/{id}/feed`, поле `horizon.next_tier`:

```json
"horizon": {
  "from": "2026-08-06", "to": "2026-12-31", "tier": "free",
  "next_tier": { "tier": "lite", "name": "Вега", "to": "2027-03-31" }
}
```

Оно с готовым русским названием. Ограничение: это ручка **ленты**, ей
нужен `chart_id`, и логически к экрану «Ещё» она не относится — в
`/profile/subscription` такого поля нет.

## Риск, который этой разведкой не проверяется: push в мобильном

`push.js` подписывается через `navigator.serviceWorker` + `PushManager` +
`Notification` (строки 25-40) — это Web Push. Ручки живые и отвечают, но
работает ли эта связка внутри WebView Capacitor — **не проверено и этим
способом непроверяемо**: нужен запуск на устройстве. Экран может читать и
писать `/push/settings` независимо от этого, но переключатель, который
сохраняется на сервере и не приводит к реальным уведомлениям, — отдельный
вопрос, решать до того, как пункт «Уведомления» станет рабочим.

---

# 4. Тариф

**Как узнать текущий тариф.** Двумя способами, оба живые:

1. `GET /auth/me` → `tier` — дешевле, и там же имя с почтой для шапки.
2. `GET /profile/subscription` → `tier` — плюс лимиты, расход и статус.

Для блока тарифа нужен второй: одного слова `"free"` мало, если показывать
что-то кроме названия.

**Сверка с `TIER_FLAGS`.** Ответ сервера для free совпал с
`TIER_FLAGS["free"]` (`backend/auth/rate_limits.py:42-61`) **по всем
полям без исключения**: `interpretation_word_limit: 500`,
`interpretations_per_month: 0`, `profiles_limit: 2`, `lunar_months: 1`,
`planner_months: 0`, `transits_months: 0`, `pdf_export: true`,
`pdf_per_month: 1`. Расхождений нет — в отличие от того, что находили в
письмах о тарифах.

⚠️ **Но верить всё равно ответу, и вот живой пример почему.**
`transits_months: 0` в ответе — это НЕ то, что видит free-пользователь.
Горизонт транзитов для free считается отдельной константой мимо флага:

```python
# backend/auth/rate_limits.py:187-189
if tier == "free":
    return FREE_TRANSITS_TEASER_MONTHS   # = 3
return TIER_FLAGS.get(tier, ...)["transits_months"]
```

То есть флаг говорит «0», а фактический горизонт — 3 месяца, и в ленте
это подтверждается: `horizon.to = 2026-12-31` при сегодняшнем 06.09.2026.
Ноль во флаге означает «AI-разбор транзитов не входит в тариф», а не
«транзитов не показывать». Ровно тот же класс расхождения, что нашли в
планере с `locked`.

**Дата окончания подписки** — `current_period_end`, на free `null`
(см. §3).

**Остаток лимитов** — только вычитанием `limits` − `usage` на клиенте,
готового числа нет (см. §3).

---

# 5. Друзья

**Функция в проекте есть.** Это реферальная программа, ручка
`GET /api/v1/profile/referral` (`profile/router.py:474`), авторизация
обязательна, гейта по тарифу нет — отвечает и на free.

Отдаёт четыре поля: `ref_code` (код), `ref_url` (готовая ссылка для
шаринга), `referrals_count` (сколько пришло), `reward_weeks_earned`
(сколько недель награды начислено).

Одна деталь из кода, которую по ответу служебного аккаунта не увидеть
(там нули): в подсчёте стоит условие `User.tier != "free"`
(`profile/router.py:497`) — то есть в счётчик и в награду, судя по всему,
попадают не все зарегистрировавшиеся по ссылке, а только перешедшие на
платный тариф. Проверить это живьём одним free-аккаунтом нельзя;
фиксирую как прочитанное в коде, а не как подтверждённое поведение.

Отдельного экрана «Друзья» в вебе нет — блок живёт внутри
`ProfilePage.jsx:782`.

---

# 6. Что из этого следует для экрана (без решений)

Только факты, решение — за спецификацией:

1. Шапка (имя + почта) и тариф закрываются **одним** `GET /auth/me`;
   если блоку тарифа нужны лимиты — вторым `GET /profile/subscription`.
2. «Мои карты» показать можно, **имя карты — нельзя**: подпись строки
   придётся строить из даты рождения и места.
3. У истории разборов подпись строки тоже не из чего собрать, кроме
   `chart_id` → та же карта без имени; `preview` перед показом надо
   чистить от `<section …>`.
4. Все пять пунктов меню имеют живые ручки — «заглушкой по причине
   отсутствия API» ни один не становится.
5. Единственное ограничение частоты во всём наборе — 3 выгрузки в час.
