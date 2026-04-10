# Astro SPA — Полная инструкция по запуску на Windows

> Инструкция написана для Windows 10/11. Все команды выполняются в **PowerShell** (не cmd), если не указано иное.

---

## Содержание

1. [Установка обязательных программ](#1-установка-обязательных-программ)
2. [Создание структуры проекта](#2-создание-структуры-проекта)
3. [Настройка файла .env](#3-настройка-файла-env)
4. [Запуск базы данных PostgreSQL через Docker](#4-запуск-базы-данных-postgresql-через-docker)
5. [Установка Python-зависимостей](#5-установка-python-зависимостей)
6. [Скачивание эфемеридных файлов](#6-скачивание-эфемеридных-файлов)
7. [Применение миграций Alembic](#7-применение-миграций-alembic)
8. [Запуск бэкенда](#8-запуск-бэкенда)
9. [Установка и запуск фронтенда](#9-установка-и-запуск-фронтенда)
10. [Ежедневный запуск (краткая версия)](#10-ежедневный-запуск-краткая-версия)
11. [Настройка внешних сервисов](#11-настройка-внешних-сервисов)
12. [Запуск тестов](#12-запуск-тестов)
13. [Частые проблемы и решения](#13-частые-проблемы-и-решения)

---

## 1. Установка обязательных программ

Устанавливайте всё по порядку — каждый следующий шаг зависит от предыдущего.

### 1.1 Git

Нужен для клонирования репозитория и работы с кодом.

1. Откройте браузер, перейдите на https://git-scm.com/download/win
2. Скачайте установщик (64-bit) и запустите его
3. На всех экранах оставляйте настройки по умолчанию
4. **Важно**: на шаге «Adjusting your PATH» выберите **«Git from the command line and also from 3rd-party software»**
5. После установки откройте новый PowerShell и проверьте:

```powershell
git --version
# Должно вывести: git version 2.xx.x.windows.x
```

---

### 1.2 Python 3.11+

1. Перейдите на https://www.python.org/downloads/
2. Скачайте Python 3.11.x или 3.12.x (кнопка «Download Python 3.x.x»)
3. Запустите установщик
4. **ОБЯЗАТЕЛЬНО** поставьте галочку **«Add Python to PATH»** внизу первого экрана
5. Нажмите «Install Now»
6. После установки закройте все окна PowerShell и откройте новый
7. Проверьте:

```powershell
python --version
# Должно вывести: Python 3.11.x или 3.12.x

pip --version
# Должно вывести: pip 24.x.x ...
```

Если `python` не найден — попробуйте `python3`. Если и это не работает — нужно добавить Python в PATH вручную (Панель управления → Система → Переменные среды → Path → добавить путь к папке Python).

---

### 1.3 Node.js 18+

Нужен для запуска фронтенда на React.

1. Перейдите на https://nodejs.org/
2. Скачайте **LTS** версию (18.x или 20.x) — кнопка слева
3. Запустите установщик, все настройки по умолчанию
4. После установки откройте новый PowerShell и проверьте:

```powershell
node --version
# Должно вывести: v18.x.x или v20.x.x

npm --version
# Должно вывести: 9.x.x или 10.x.x
```

---

### 1.4 Docker Desktop

Нужен для запуска PostgreSQL без его ручной установки.

1. Перейдите на https://www.docker.com/products/docker-desktop/
2. Нажмите «Download for Windows»
3. Запустите установщик `Docker Desktop Installer.exe`
4. Выберите **«Use WSL 2 instead of Hyper-V»** если предлагается (рекомендуется)
5. После установки **перезагрузите компьютер**
6. После перезагрузки запустите Docker Desktop из меню Пуск
7. Подождите пока в трее появится зелёная иконка кита (это означает что Docker работает)
8. Проверьте в PowerShell:

```powershell
docker --version
# Должно вывести: Docker version 24.x.x, build ...

docker compose version
# Должно вывести: Docker Compose version v2.x.x
```

> **Если Docker требует WSL 2**: откройте PowerShell **от имени администратора** и выполните:
> ```powershell
> wsl --install
> ```
> После этого перезагрузите компьютер.

---

### 1.5 PowerShell (настройка политик)

По умолчанию Windows блокирует запуск скриптов. Нужно разрешить:

1. Откройте PowerShell **от имени администратора** (правой кнопкой по PowerShell → «Запуск от имени администратора»)
2. Выполните:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

3. На вопрос ответьте `Y` и нажмите Enter

---

## 2. Создание структуры проекта

### 2.1 Клонирование репозитория

Откройте PowerShell и перейдите в папку, где хотите разместить проект (например, рабочий стол или папка `C:\Projects`):

```powershell
# Перейти в папку (замените путь на свой)
cd C:\Users\ВашеИмя\Documents

# Клонировать репозиторий
git clone <ссылка-на-репозиторий> astro-spa

# Перейти в папку проекта
cd astro-spa
```

Если репозитория ещё нет — создайте папку вручную:

```powershell
mkdir C:\Users\ВашеИмя\Documents\astro-spa
cd C:\Users\ВашеИмя\Documents\astro-spa
```

И скопируйте туда все файлы проекта из архива или загруженных файлов.

### 2.2 Проверка структуры

После того как все файлы на месте, убедитесь что структура правильная:

```powershell
# Проверяем что мы в корне проекта
ls
# Должны увидеть: backend/, frontend/, alembic/, alembic.ini, docker-compose.yml и т.д.
```

---

## 3. Настройка файла .env

Файл `.env` содержит все секреты и настройки проекта. Он **не должен попасть в git** (уже добавлен в `.gitignore`).

### 3.1 Создание .env

```powershell
# Копируем шаблон (если есть .env.example)
Copy-Item .env.example .env

# Если .env.example нет — создаём вручную
New-Item -ItemType File -Name ".env"
```

### 3.2 Открытие .env для редактирования

```powershell
# Открыть в Блокноте
notepad .env

# Или в VS Code (если установлен)
code .env
```

### 3.3 Содержимое .env — полный шаблон

Скопируйте это в файл и заполните значения:

```env
# ─── База данных ─────────────────────────────────────────
DATABASE_URL=postgresql://astro:astro@localhost:5432/astro_db

# ─── JWT ─────────────────────────────────────────────────
# Генерация секрета — выполните в PowerShell:
# python -c "import secrets; print(secrets.token_urlsafe(64))"
JWT_SECRET=ЗАМЕНИТЕ-НА-СГЕНЕРИРОВАННЫЙ-СЕКРЕТ
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=15
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# ─── AI провайдеры ───────────────────────────────────────
# Получите на https://platform.openai.com
OPENAI_API_KEY=sk-...

# Получите на https://platform.deepseek.com (опционально)
DEEPSEEK_API_KEY=sk-...

# ─── Google OAuth (опционально на старте) ────────────────
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=

# ─── Stripe (опционально на старте) ──────────────────────
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_ID_PRO=price_...
STRIPE_PRICE_ID_PREMIUM=price_...

# ─── CORS ────────────────────────────────────────────────
# Адреса фронтенда, которым разрешены запросы к API
CORS_ORIGINS=["http://localhost:5173","http://localhost:3000"]

# ─── Rate limits ─────────────────────────────────────────
RATE_LIMIT_ANON=30/minute
RATE_LIMIT_FREE_CHARTS_PER_DAY=5
RATE_LIMIT_FREE_INTERPRETATIONS_PER_DAY=2

# ─── Эфемериды ───────────────────────────────────────────
EPHE_PATH=data/ephe

# ─── Режим ───────────────────────────────────────────────
DEBUG=true
```

### 3.4 Генерация JWT_SECRET

В PowerShell выполните:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

Скопируйте вывод и вставьте вместо `ЗАМЕНИТЕ-НА-СГЕНЕРИРОВАННЫЙ-СЕКРЕТ` в файл `.env`.

---

## 4. Запуск базы данных PostgreSQL через Docker

### 4.1 Проверка docker-compose.yml

Убедитесь что в корне проекта есть файл `docker-compose.yml`. Минимальное содержимое должно быть таким:

```yaml
version: "3.9"
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: astro
      POSTGRES_PASSWORD: astro
      POSTGRES_DB: astro_db
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

volumes:
  postgres_data:
```

Если файла нет — создайте его с этим содержимым.

### 4.2 Запуск контейнера

**Docker Desktop должен быть запущен** (иконка кита в трее).

```powershell
# Из корня проекта (где лежит docker-compose.yml)
docker compose up -d db
```

Флаг `-d` означает «запустить в фоне».

### 4.3 Проверка что база запустилась

```powershell
# Смотрим логи контейнера
docker compose logs db
```

В конце логов должно быть:
```
database system is ready to accept connections
```

Или проверьте статус:
```powershell
docker compose ps
# Должно показать: db   running   0.0.0.0:5432->5432/tcp
```

### 4.4 Если порт 5432 уже занят

Если на компьютере уже установлен PostgreSQL — порт может быть занят. Измените в `docker-compose.yml`:

```yaml
ports:
  - "5433:5432"   # внешний порт 5433 вместо 5432
```

И обновите `DATABASE_URL` в `.env`:
```
DATABASE_URL=postgresql://astro:astro@localhost:5433/astro_db
```

---

## 5. Установка Python-зависимостей

### 5.1 Создание виртуального окружения

Виртуальное окружение изолирует пакеты проекта от системного Python.

```powershell
# Находимся в корне проекта astro-spa/
python -m venv .venv
```

После выполнения появится папка `.venv`.

### 5.2 Активация окружения

**Важно**: активировать нужно в каждом новом окне PowerShell перед работой с проектом.

```powershell
.venv\Scripts\Activate.ps1
```

После активации в начале строки появится `(.venv)`:
```
(.venv) PS C:\Users\...\astro-spa>
```

> **Если появляется ошибка «не может быть загружен, так как выполнение скриптов отключено»**:
> ```powershell
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```
> Затем снова активируйте окружение.

### 5.3 Обновление pip

```powershell
python -m pip install --upgrade pip
```

### 5.4 Установка зависимостей

#### Если есть `pyproject.toml`:

```powershell
pip install -e ".[dev]"
```

#### Если есть `requirements.txt`:

```powershell
pip install -r requirements.txt
```

#### Если нет ни того, ни другого — установите вручную:

```powershell
pip install fastapi uvicorn[standard] sqlalchemy alembic psycopg2-binary `
    pydantic pydantic-settings python-jose[cryptography] passlib[bcrypt] `
    httpx stripe slowapi pyswisseph timezonefinder pytz python-dotenv `
    pytest pytest-asyncio pytest-cov
```

> **Важно для pyswisseph на Windows**: эта библиотека требует Visual C++ Build Tools. Если установка падает с ошибкой — прочитайте раздел [13. Частые проблемы](#13-частые-проблемы-и-решения).

### 5.5 Проверка установки

```powershell
python -c "import fastapi; print('FastAPI OK')"
python -c "import swisseph; print('pyswisseph OK')"
python -c "import stripe; print('Stripe OK')"
```

---

## 6. Скачивание эфемеридных файлов

Swiss Ephemeris требует файлы данных для расчётов. Без них расчёт карт невозможен.

### 6.1 Создание папки

```powershell
# Из корня проекта
mkdir data\ephe
```

### 6.2 Скачивание файлов

Перейдите в браузере на: https://www.astro.com/ftp/swisseph/ephe/

Скачайте файлы `.se1` — это бинарные файлы эфемерид. Минимальный набор:

| Файл | Размер | Содержит |
|------|--------|----------|
| `sepl_18.se1` | ~3 МБ | Планеты 1800–1900 |
| `sepl_20.se1` | ~3 МБ | Планеты 2000–2100 |
| `semo_18.se1` | ~2 МБ | Луна 1800–1900 |
| `semo_20.se1` | ~2 МБ | Луна 2000–2100 |
| `seas_18.se1` | ~2 МБ | Астероиды 1800–1900 |
| `seas_20.se1` | ~2 МБ | Астероиды 2000–2100 |

**Для полного покрытия** (рекомендуется) скачайте все файлы `sepl*.se1`, `semo*.se1`, `seas*.se1`.

### 6.3 Размещение файлов

Скачанные файлы `.se1` поместите в папку `data\ephe\` вашего проекта:

```
astro-spa\
└── data\
    └── ephe\
        ├── sepl_18.se1
        ├── sepl_20.se1
        ├── semo_18.se1
        ├── semo_20.se1
        ├── seas_18.se1
        └── seas_20.se1
```

### 6.4 Проверка

```powershell
ls data\ephe\
# Должны появиться .se1 файлы
```

---

## 7. Применение миграций Alembic

Миграции создают таблицы в базе данных. Это нужно сделать **один раз** при первом запуске и повторно при добавлении новых миграций.

### 7.1 Убедитесь что база данных запущена

```powershell
docker compose ps
# db должен быть в состоянии running
```

### 7.2 Убедитесь что виртуальное окружение активно

```powershell
# В начале строки должно быть (.venv)
# Если нет — активируйте:
.venv\Scripts\Activate.ps1
```

### 7.3 Проверка alembic.ini

Откройте `alembic.ini` и найдите строку:
```ini
sqlalchemy.url = postgresql://astro:astro@localhost:5432/astro_db
```

Если вы изменили порт или пароль — обновите эту строку. Либо убедитесь что `alembic/env.py` читает `DATABASE_URL` из переменных окружения (так правильнее).

### 7.4 Применение миграций

```powershell
# Из корня проекта (где лежит alembic.ini)
alembic upgrade head
```

Вывод должен быть примерно таким:
```
INFO  [alembic.runtime.migration] Context impl PostgreSQLImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade  -> 001_initial, Initial tables
INFO  [alembic.runtime.migration] Running upgrade 001_initial -> 002_subscriptions, Add subscriptions
INFO  [alembic.runtime.migration] Running upgrade 002_subscriptions -> 003_users_auth_stripe, Add auth columns
```

### 7.5 Проверка

```powershell
alembic current
# Должно показать последнюю версию миграции

# Или проверьте таблицы напрямую:
docker exec -it astro-spa-db-1 psql -U astro -d astro_db -c "\dt"
# Должны увидеть: users, natal_charts, interpretations, subscriptions
```

> **Название контейнера** может отличаться. Узнайте его через `docker ps`.

---

## 8. Запуск бэкенда

### 8.1 Активируйте виртуальное окружение (если не активно)

```powershell
.venv\Scripts\Activate.ps1
```

### 8.2 Запуск uvicorn

```powershell
# Из корня проекта
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

Флаг `--reload` включает автоматическую перезагрузку при изменении кода.

Правильный вывод:
```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Started reloader process [12345]
INFO:     Started server process [12346]
INFO:     Waiting for application startup.
INFO:     Database tables ensured.
INFO:     Application startup complete.
```

### 8.3 Проверка работы API

Откройте браузер и перейдите:

- **Health check**: http://localhost:8000/health
  - Должно вернуть: `{"status":"ok","version":"0.3.0","database":"not_checked"}`

- **Swagger UI** (интерактивная документация): http://localhost:8000/docs
  - Здесь можно тестировать все эндпоинты прямо в браузере

- **DB health**: http://localhost:8000/health/db
  - Должно вернуть: `{"status":"ok","database":"connected"}`

### 8.4 Если бэкенд не запускается

Самые частые причины:

**Ошибка «Module not found»**:
```powershell
# Убедитесь что окружение активно и вы в корне проекта
# Попробуйте запустить через python -m:
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

**Ошибка подключения к БД**:
```powershell
# Проверьте что Docker запущен и контейнер работает
docker compose ps
```

---

## 9. Установка и запуск фронтенда

Фронтенд запускается **в отдельном окне PowerShell**, параллельно с бэкендом.

### 9.1 Откройте новый PowerShell

Не закрывайте бэкенд. Откройте новое окно PowerShell (Win+X → Windows PowerShell).

### 9.2 Перейдите в папку фронтенда

```powershell
cd C:\Users\ВашеИмя\Documents\astro-spa\frontend
```

### 9.3 Установка npm-пакетов

```powershell
npm install
```

Это займёт 1-3 минуты. Появится папка `node_modules`. Делается **один раз** (повторно только если изменился `package.json`).

### 9.4 Проверка package.json

Убедитесь что в `frontend/package.json` есть нужные зависимости. Минимально необходимые:

```json
{
  "dependencies": {
    "react": "^18.0.0",
    "react-dom": "^18.0.0",
    "react-router-dom": "^6.0.0"
  },
  "devDependencies": {
    "vite": "^5.0.0",
    "@vitejs/plugin-react": "^4.0.0",
    "tailwindcss": "^3.0.0"
  }
}
```

Если чего-то не хватает:
```powershell
npm install react-router-dom
npm install -D tailwindcss
```

### 9.5 Настройка Vite proxy

Чтобы запросы фронтенда к `/api/v1/...` шли на бэкенд, нужен прокси в `vite.config.js`.

Откройте `frontend/vite.config.js` и убедитесь что есть:

```javascript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/health': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
```

Если файла нет — создайте его с этим содержимым.

### 9.6 Запуск фронтенда

```powershell
npm run dev
```

Правильный вывод:
```
  VITE v5.x.x  ready in 500 ms

  ➜  Local:   http://localhost:5173/
  ➜  Network: use --host to expose
```

### 9.7 Открытие в браузере

Перейдите на http://localhost:5173 — должно открыться приложение.

---

## 10. Ежедневный запуск (краткая версия)

После первоначальной настройки каждый раз для работы нужно:

**Терминал 1 — База данных:**
```powershell
cd C:\Users\ВашеИмя\Documents\astro-spa
docker compose up -d db
```

**Терминал 2 — Бэкенд:**
```powershell
cd C:\Users\ВашеИмя\Documents\astro-spa
.venv\Scripts\Activate.ps1
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

**Терминал 3 — Фронтенд:**
```powershell
cd C:\Users\ВашеИмя\Documents\astro-spa\frontend
npm run dev
```

**Остановка всего:**
- Бэкенд и фронтенд: `Ctrl+C` в каждом терминале
- База данных: `docker compose stop` (в Терминале 1 или в новом окне из корня проекта)

---

## 11. Настройка внешних сервисов

Можно запустить проект и без них — бэкенд работает, шаблонные интерпретации доступны. Но для полного функционала нужно:

### 11.1 OpenAI API Key (для AI-интерпретаций)

1. Зайдите на https://platform.openai.com/signup и зарегистрируйтесь
2. Перейдите в https://platform.openai.com/api-keys
3. Нажмите «Create new secret key», скопируйте ключ (он показывается только один раз!)
4. Добавьте в `.env`:
   ```
   OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx
   ```
5. Пополните баланс на $5-10 для тестирования (https://platform.openai.com/billing)

### 11.2 Google OAuth (для входа через Google)

1. Перейдите на https://console.cloud.google.com/
2. Создайте новый проект (или выберите существующий)
3. Перейдите в **APIs & Services → Credentials**
4. Нажмите **«+ Create Credentials» → «OAuth client ID»**
5. Тип приложения: **Web application**
6. В «Authorized redirect URIs» добавьте:
   - `http://localhost:5173/oauth/callback`
7. Нажмите «Create» — скопируйте Client ID и Client Secret
8. Добавьте в `.env`:
   ```
   GOOGLE_CLIENT_ID=xxxxxxxxxx.apps.googleusercontent.com
   GOOGLE_CLIENT_SECRET=GOCSPX-xxxxxxxxxx
   ```
9. В `frontend/vite.config.js` или в `.env` фронтенда добавьте:
   ```
   VITE_GOOGLE_CLIENT_ID=xxxxxxxxxx.apps.googleusercontent.com
   ```

### 11.3 Stripe (для оплаты)

1. Зарегистрируйтесь на https://stripe.com
2. В Dashboard перейдите в **Developers → API keys**
3. Скопируйте **Secret key** (начинается с `sk_test_...`)
4. Создайте продукты:
   - Dashboard → **Products → Add product**
   - Название: «Pro», цена €7.99/мес, recurring
   - Скопируйте **Price ID** (начинается с `price_...`)
   - Повторите для Premium (€19.99/мес)
5. Настройте вебхуки для локального тестирования:
   - Скачайте Stripe CLI: https://stripe.com/docs/stripe-cli#install
   - Для Windows: скачайте `.exe` файл и добавьте в PATH
   - Войдите: `stripe login`
   - Запустите переадресацию (в отдельном терминале):
     ```powershell
     stripe listen --forward-to localhost:8000/api/v1/payments/webhook
     ```
   - Скопируйте `whsec_...` из вывода
6. Добавьте в `.env`:
   ```
   STRIPE_SECRET_KEY=sk_test_xxxxxxxxxx
   STRIPE_WEBHOOK_SECRET=whsec_xxxxxxxxxx
   STRIPE_PRICE_ID_PRO=price_xxxxxxxxxx
   STRIPE_PRICE_ID_PREMIUM=price_xxxxxxxxxx
   ```

---

## 12. Запуск тестов

### 12.1 Активируйте окружение

```powershell
cd C:\Users\ВашеИмя\Documents\astro-spa
.venv\Scripts\Activate.ps1
```

### 12.2 Запуск всех тестов

```powershell
pytest
```

### 12.3 Запуск с подробным выводом

```powershell
pytest -v
```

### 12.4 Запуск конкретного файла тестов

```powershell
pytest tests/test_auth.py -v
pytest tests/test_payments.py -v
pytest tests/test_profile.py -v
pytest tests/test_transits.py -v
```

### 12.5 Запуск с покрытием кода

```powershell
pytest --cov=backend --cov-report=html
# После завершения откройте htmlcov\index.html в браузере
```

### 12.6 Пропустить медленные тесты

```powershell
pytest -m "not slow"
```

---

## 13. Частые проблемы и решения

### ❌ Ошибка при установке pyswisseph: «Microsoft Visual C++ required»

**Причина**: pyswisseph содержит C-расширения и требует компилятор.

**Решение 1** (быстрое): установите Visual C++ Build Tools:
1. Перейдите на https://visualstudio.microsoft.com/visual-cpp-build-tools/
2. Скачайте и запустите установщик
3. Выберите **«Desktop development with C++»**
4. Установите (~4-6 ГБ)
5. Перезагрузите PowerShell и повторите `pip install pyswisseph`

**Решение 2** (если Build Tools не помогло): найдите готовый wheel на PyPI:
```powershell
pip install pyswisseph --only-binary :all:
```

---

### ❌ Ошибка «Cannot connect to the Docker daemon»

**Причина**: Docker Desktop не запущен.

**Решение**: найдите Docker Desktop в меню Пуск и запустите его. Подождите пока в трее появится зелёная иконка кита.

---

### ❌ Ошибка «port is already allocated» при запуске Docker

**Причина**: порт 5432 занят другим процессом (например, локальным PostgreSQL).

**Решение**: измените порт в `docker-compose.yml`:
```yaml
ports:
  - "5433:5432"
```
И в `.env`:
```
DATABASE_URL=postgresql://astro:astro@localhost:5433/astro_db
```

---

### ❌ Ошибка «python: command not found» или «python не является командой»

**Причина**: Python не добавлен в PATH.

**Решение**:
1. Откройте «Параметры Windows» → «Система» → «О системе» → «Дополнительные параметры системы»
2. «Переменные среды» → найдите «Path» в списке системных переменных → «Изменить»
3. Добавьте строки (замените `3.11` на вашу версию):
   ```
   C:\Users\ВашеИмя\AppData\Local\Programs\Python\Python311\
   C:\Users\ВашеИмя\AppData\Local\Programs\Python\Python311\Scripts\
   ```
4. Нажмите OK везде и откройте новый PowerShell

---

### ❌ Ошибка «alembic: command not found»

**Причина**: виртуальное окружение не активировано.

**Решение**:
```powershell
.venv\Scripts\Activate.ps1
alembic upgrade head
```

---

### ❌ Ошибка «SQLALCHEMY_DATABASE_URL» или «DATABASE_URL not set»

**Причина**: `.env` файл не найден или не загружен.

**Решение**: убедитесь что `.env` лежит в **корне проекта** (там же где `backend/`, `frontend/`, `alembic.ini`). Также проверьте что в `backend/config.py` используется `python-dotenv` для загрузки переменных:

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    class Config:
        env_file = ".env"
```

---

### ❌ Фронтенд открывается, но API не работает (ошибки CORS или 404)

**Причина**: прокси в `vite.config.js` не настроен.

**Решение**: добавьте proxy в `frontend/vite.config.js` (см. шаг 9.5).

---

### ❌ «npm: command not found»

**Причина**: Node.js не установлен или не добавлен в PATH.

**Решение**: переустановите Node.js с официального сайта https://nodejs.org/, открыв установщик от имени администратора. После установки закройте и откройте PowerShell заново.

---

### ❌ Ошибка «Cannot find module» в React

**Причина**: зависимости не установлены или установлены не там.

**Решение**:
```powershell
# Убедитесь что вы в папке frontend/
cd frontend

# Удалите node_modules и переустановите
Remove-Item -Recurse -Force node_modules
npm install
```

---

### ❌ Ошибка «swisseph.set_ephe_path» или «ephemeris file not found»

**Причина**: эфемеридные файлы не скачаны или путь неверный.

**Решение**:
1. Убедитесь что файлы `.se1` находятся в `data\ephe\`
2. Проверьте переменную в `.env`: `EPHE_PATH=data/ephe`
3. Проверьте что путь указан с **прямыми слешами** `/`, не обратными `\`

---

## Финальная проверка — чеклист

После выполнения всех шагов убедитесь:

- [ ] Docker Desktop запущен (зелёная иконка в трее)
- [ ] `docker compose ps` показывает `db` в состоянии `running`
- [ ] http://localhost:8000/health возвращает `{"status":"ok"}`
- [ ] http://localhost:8000/health/db возвращает `{"database":"connected"}`
- [ ] http://localhost:8000/docs открывает Swagger UI со всеми эндпоинтами
- [ ] http://localhost:5173 открывает форму ввода данных рождения
- [ ] Форма принимает данные и возвращает карту (без AI-ключа работает шаблонный движок)
- [ ] `pytest tests/test_validation.py -v` проходит без ошибок
