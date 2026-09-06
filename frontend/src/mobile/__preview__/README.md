# `__preview__` — стенд приёмки экранов мобильного приложения

Файлы этой папки **в репозиторий не идут** (см. `.gitignore` внутри самой
папки) — это подмена `window.fetch` ради визуальной приёмки, не часть
приложения. Владелец попросил не удалять их с диска до конца приёмки.

## Зачем это вообще нужно

Боевой API (`aristeatime.ru`) не пускает dev-origin по CORS
(`http://localhost:5173` — проверено, ответ без
`access-control-allow-origin`). Поэтому `FeedPreview.jsx`/`ChartPreview.jsx`
подменяют `window.fetch` и отдают настоящий боевой ответ, снятый заранее в
`fixture.json`/`chart_fixture.json` — сам экран (`FeedScreen.jsx` и т.п.)
работает без единой правки, включая состояния, группировку и прокрутку.

## Чем генерируется `fixture.json`

Прямой HTTPS-запрос к боевому API (без браузера — CORS его не пускает, но
это ограничение только браузера, `curl`/`python` его не видят):

1. `POST /api/v1/auth/login` — логин под служебным тестовым аккаунтом.
   Email и пароль лежат в **корневом `.env` проекта**, переменные
   `TEST_ACCOUNT_EMAIL` / `TEST_ACCOUNT_PASSWORD`. Не в этом README, не в
   команде, не в чате — только по имени переменной. Это тот же аккаунт,
   которым снята разведка по экрану «Карта» (`CHART_API_RECON.md`).
2. `GET /api/v1/profile/charts` — список карт аккаунта. Карта, снимок
   которой лежит в фикстуре, — `b1ae94f2-d64f-4f31-81e2-8555ca8a1e37`
   (первая из двух карт аккаунта; какая именно — не принципиально, важно
   не менять между перегенерациями, чтобы скриншоты были сравнимы).
3. `GET /api/v1/chart/{id}/feed?from_date=…&to_date=…` — сама лента, окно
   ровно то же, что считает клиент: `feedWindow()`
   (`frontend/src/mobile/lib/feedApi.js`) — сегодня минус 31 день, сегодня
   плюс 334 дня. Не «сколько влезет» и не фиксированные даты — от текущей
   даты запуска, иначе повторный снятие через месяц даст не совпадающее с
   тем, что видит реальный пользователь, окно.
4. Оба ответа складываются в один файл: `{"charts": <ответ п.2>, "feed":
   <ответ п.3>}` — именно в этой форме их читает `window.fetch` внутри
   `FeedPreview.jsx` (роуты `/profile/charts` и `/feed` по подстроке в URL).

Готового скрипта в репозитории нет — каждый раз это одноразовый
Python-скрипт (`urllib`, без внешних зависимостей), примерно:

```python
import os, json, datetime, urllib.request

def load_dotenv(path=".env"):
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

load_dotenv()
EMAIL = os.environ["TEST_ACCOUNT_EMAIL"]
PASSWORD = os.environ["TEST_ACCOUNT_PASSWORD"]
# ... POST /auth/login -> access_token, затем GET /profile/charts
# и GET /chart/{id}/feed?from_date=...&to_date=... с Authorization: Bearer
```

Пароль никогда не должен попадать в отчёт, лог команды или сообщение чата —
только имя переменной окружения.

## Что регенерировать при следующей приёмке

- `fixture.json` стареет вместе с окном: событие «сегодня» на скриншоте —
  это дата запуска скрипта, не дата в файле. Если снимки должны показывать
  конкретный день — регенерировать в этот же день.
- `chart_fixture.json` (для `ChartScreen`) генерируется тем же приёмом,
  другой ручкой (см. `ChartPreview.jsx` и `CHART_API_RECON.md`).
