# Обновление Astro SPA → режим эксперта (AspectTable)

## Что сделано

Реализован **Вариант В**: таблица аспектов скрыта за переключателем «Режим эксперта»
в заголовке страницы карты. Предпочтение сохраняется в `localStorage` и синхронизируется
с профилем пользователя через API (если авторизован).

---

## Файлы в этом архиве

```
astro-planner-update/
│
├── frontend/src/
│   ├── hooks/
│   │   └── useExpertMode.js          ← новый хук
│   ├── components/
│   │   ├── ExpertModeToggle.jsx      ← новый компонент-кнопка
│   │   └── AspectTableWrapper.jsx    ← новая обёртка с анимацией
│   └── pages/
│       └── ChartPage.jsx             ← обновлённая страница (заменить целиком)
│
├── backend/
│   ├── profile/
│   │   └── settings_router.py        ← новый роутер настроек
│   ├── models_patch.py               ← ИНСТРУКЦИЯ (не копировать, прочитать)
│   └── main_patch.py                 ← ИНСТРУКЦИЯ (не копировать, прочитать)
│
└── alembic/versions/
    └── 004_expert_mode.py            ← миграция БД
```

---

## Порядок развёртывания

### Шаг 1 — Бэкенд: добавить поле в модель

Открой `backend/models.py`, найди класс `User`, добавь одну строку:

```python
# UI preferences
expert_mode = Column(Boolean, default=False, nullable=False, server_default="false")
```

Подробности — в файле `backend/models_patch.py`.

### Шаг 2 — Бэкенд: применить миграцию БД

Скопируй `alembic/versions/004_expert_mode.py` в папку `alembic/versions/` проекта.

Убедись, что в файле поле `down_revision` указывает на твою последнюю миграцию
(сейчас стоит `'003_users_auth_stripe'` — если у тебя другое имя, исправь).

```bash
# Из корня проекта:
alembic upgrade head
```

Проверка:
```bash
alembic current   # должно показать 004_expert_mode (head)
```

### Шаг 3 — Бэкенд: добавить роутер настроек

Скопируй `backend/profile/settings_router.py` в папку `backend/profile/` проекта.

Открой `backend/main.py` и добавь две строки из файла `backend/main_patch.py`.

Перезапусти сервер:
```bash
uvicorn backend.main:app --reload
```

Проверка (должны появиться два новых эндпоинта):
```bash
curl http://localhost:8000/openapi.json | grep settings
# или открой http://localhost:8000/docs → раздел profile
```

### Шаг 4 — Фронтенд: скопировать файлы

| Откуда (этот архив) | Куда (твой проект) | Действие |
|---|---|---|
| `frontend/src/hooks/useExpertMode.js` | `frontend/src/hooks/useExpertMode.js` | создать файл |
| `frontend/src/components/ExpertModeToggle.jsx` | `frontend/src/components/ExpertModeToggle.jsx` | создать файл |
| `frontend/src/components/AspectTableWrapper.jsx` | `frontend/src/components/AspectTableWrapper.jsx` | создать файл |
| `frontend/src/pages/ChartPage.jsx` | `frontend/src/pages/ChartPage.jsx` | **заменить** существующий |

> ⚠️ Папка `hooks/` может не существовать — создай её.

### Шаг 5 — Фронтенд: проверить пропсы ChartPage

Обновлённый `ChartPage` принимает проп `currentUser` (объект с полем `id`).
Убедись, что родительский компонент (обычно `App.jsx` или роутер) передаёт его:

```jsx
// App.jsx или router
<ChartPage chartId={id} currentUser={user} />
```

Если `currentUser` не передаётся — режим эксперта будет работать только через
`localStorage` (без синхронизации между устройствами). Это нормально.

### Шаг 6 — Запустить фронтенд

```bash
cd frontend
npm run dev      # dev-сервер
# или
npm run build    # production build
```

---

## Поведение после обновления

| Состояние | Что видит пользователь |
|---|---|
| Режим эксперта **выключен** (по умолчанию) | Таблица аспектов скрыта, секция занимает 0px высоты |
| Нажал «Режим эксперта» в шапке | Таблица плавно раскрывается (~350мс), появляется метка «эксперт» |
| Перезагрузил страницу | Состояние восстанавливается из localStorage мгновенно |
| Авторизованный пользователь, второй браузер | Состояние подтягивается из профиля через GET /api/v1/profile/settings |

---

## Расширение в будущем

Хук `useExpertMode` и эндпоинт `PATCH /profile/settings` спроектированы
под рост: в `UserSettings` (Pydantic) и в модели `User` можно добавлять новые
поля настроек без дополнительных роутеров.

Пример — добавление тёмной темы или системы домов:
```python
# backend/profile/settings_router.py → UserSettings
class UserSettings(BaseModel):
    expert_mode: Optional[bool] = None
    theme: Optional[str] = None          # "light" | "dark" | "auto"
    house_system: Optional[str] = None   # "placidus" | "whole_sign" | ...
```
