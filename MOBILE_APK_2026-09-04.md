# Мобильная сборка: каркас Capacitor + Android APK

**Дата:** 04.09.2026
**Ветка:** `mobile` (в `main` не мержится)
**Коммит:** `93dbaed` — feat(mobile): каркас Android-сборки на Capacitor
**Прогон:** https://github.com/alex753ad/astro/actions/runs/33861181196 — зелёный с первого раза
**Артефакт:** `astrea-debug-apk` → `app-debug.apk`, 4.38 МБ, хранится 30 дней

Задача: доказать, что цепочка сборки `vite → dist-mobile → cap sync → APK →
webview` работает. Экранов приложения в задании нет.

---

## Как получить APK

```
gh run download 33861181196 -n astrea-debug-apk
```

Или вручную: **Actions → Mobile APK → прогон → Artifacts**.

Пересобрать: **Actions → Mobile APK → Run workflow** (ветка `mobile`), либо
любой push в `mobile`, либо:

```
gh workflow run mobile-build.yml --ref mobile
gh run watch
```

---

## Приёмка

### Проверено фактически

| Что | Чем |
|---|---|
| Все 12 шагов workflow, включая `assembleDebug` | прогон 33861181196 |
| В APK лежит абсолютный URL API | распаковка APK: `assets/public/assets/index.mobile-*.js` содержит `https://www.aristeatime.ru/api/v1` |
| Относительного `/api/v1` в мобильном бандле нет | grep по `dist-mobile` — 0 вхождений; отдельный шаг workflow падает, если строка исчезнет |
| `arm64-v8a` поддержан | в APK **нет каталога `lib/`** — нативных `.so` сборка не содержит, `abiFilters` не задан, APK универсальный по ABI |
| `minSdk 23`, `targetSdk 35`, `compileSdk 35` | `variables.gradle`, проверяется шагом workflow, а не только глазами |
| `applicationId ru.aristeatime.app` | `android/app/build.gradle` |
| Веб-сборка не изменилась | прогнал `npm run build`: в `dist/assets/*.js` абсолютного URL **0 вхождений**; `git status` по `frontend/dist` и `frontend/public/sitemap.xml` чист |
| `notify.py` читает из `.env` | отправка прошла, сообщения дошли |
| Игноры работают | `git check-ignore` на `dist-mobile/`, `android/`, `*.keystore` |

### НЕ проверено — и почему

**APK на устройстве не запускался.** Android-тулчейна и эмулятора локально
нет (по вашему решению — ставить не будем), в CI эмулятор не поднимался.

**И при сегодняшнем состоянии сервера первый экран покажет красное «Запрос не
прошёл».** Это не дефект сборки — это ожидаемое поведение до правки CORS,
см. следующий раздел. Приёмка «приложение достаёт данные с боевого API»
закрывается только после неё.

---

## ⚠️ Что осталось за владельцем: CORS

Webview Capacitor грузит страницу с origin `https://localhost`
(`androidScheme` по умолчанию `https`, подтверждено по `CapConfig.java`).
Этого origin в списке прода нет. Проверено запросами с этой машины
**до** сборки:

| `Origin` запроса | Ответ | `Access-Control-Allow-Origin` |
|---|---|---|
| `https://localhost` | 200 | **пусто** → браузер блокирует чтение тела |
| `http://localhost` | 200 | **пусто** |
| `https://www.aristeatime.ru` | 200 | `https://www.aristeatime.ru` |

Тело до webview доходит, но JS его не увидит — в приложении это выглядит как
`TypeError` без статуса и без причины. Поэтому на экране рядом с ошибкой
печатается сам URL: по нему сразу видно, ушёл запрос на боевой домен или на
относительный путь.

### Блок команд — вставить целиком

`sed` здесь не годится: значение содержит кавычки и слеши, а правило проекта
(CLAUDE.md, «Правка файлов скриптом») это запрещает прямым текстом. Скрипт
ниже сам определяет формат значения и сохраняет его — бэкенд понимает оба
имени ключа (`backend/config.py:109`, `AliasChoices`) и оба формата значения
(JSON-массив и список через запятую, `cors_origins_list`), поэтому одна
команда закрывает оба случая и не переписывает формат без нужды.

```
grep -E '^(ALLOWED_ORIGINS|CORS_ORIGINS)=' /opt/astro/.env

cp -a /opt/astro/.env /opt/astro/.env.bak-$(date +%Y%m%d)

python3 - <<'PYEOF'
import json, re
from pathlib import Path

p = Path("/opt/astro/.env")
t = p.read_text(encoding="utf-8")
NEW = ["https://localhost", "http://localhost"]

pat = re.compile("^(ALLOWED_ORIGINS|CORS_ORIGINS)=(.*)$", re.MULTILINE)
hits = pat.findall(t)
assert len(hits) == 1, "строк с ключом: " + str(len(hits)) + " (ожидалась ровно 1)"

key, raw = hits[0]
old_line = key + "=" + raw
raw_s = raw.strip()

if raw_s.startswith("["):
    fmt = "JSON-массив"
    origins = [str(o).strip() for o in json.loads(raw_s) if str(o).strip()]
else:
    fmt = "список через запятую"
    origins = [o.strip() for o in raw_s.split(",") if o.strip()]

assert origins, "список origins пуст — проверьте строку руками"
assert "*" not in origins, "в списке есть * — backend/main.py:409 уронит старт"

added = [o for o in NEW if o not in origins]
assert added, "оба origin уже в списке — править нечего"
origins = origins + added

new_value = json.dumps(origins) if raw_s.startswith("[") else ",".join(origins)
new_line = key + "=" + new_value

assert t.count(old_line) == 1, "якорь: " + str(t.count(old_line))
t2 = t.replace(old_line, new_line)
assert t2 != t, "замена не применилась"
p.write_text(t2, encoding="utf-8")

print("формат:", fmt)
print("ключ:", key)
print("добавлено:", ", ".join(added))
print("стало:", new_line)
PYEOF

grep -E '^(ALLOWED_ORIGINS|CORS_ORIGINS)=' /opt/astro/.env

cd /opt/astro && docker compose up -d --force-recreate api
```

Что в нём сделано намеренно:

- **Обе проверки из CLAUDE.md, и одна другую не заменяет.** `count == 1`
  ловит отсутствующий или неоднозначный якорь (ключ задан дважды — молча
  победит не та строка); `t2 != t` ловит несработавшую замену — ровно тот
  случай 23.08.2026, когда `assert count == 1` прошёл, а `replace` не сделал
  ничего и скрипт отрапортовал успехом.
- **Ни одного обратного слеша в python-коде.** Регулярка обходится без
  экранирования, сообщения собираются конкатенацией. В heredoc этого
  окружения слеши съедаются — однажды это записало литеральный `\n` в
  середину `05-update.sh`.
- **Формат определяется и сохраняется, а не навязывается.** Переписывание
  JSON-массива в список через запятую — лишнее изменение, которого никто не
  просил.
- **`assert "*" not in origins`** — страховка от правки поверх уже сломанной
  конфигурации: с `*` при `allow_credentials=True` контейнер не поднимется
  (`main.py:409`, в проде `RuntimeError`, в тестовом режиме `logger.error`),
  и это выглядело бы как «сломалось от добавления localhost».
- **`assert added`** — повторный запуск не продублирует origins.
- **`cp -a`, а не `cp`** — сохраняет владельца и права. `.env` читают и
  контейнеры, и `05-update.sh`; файл с изменёнными правами — знакомый в этом
  проекте способ сломать деплой.
- **Пересоздаётся только `api`** — воркеру, beat и боту CORS не нужен.

**Именно `--force-recreate`, а не `down`.** `env_file` читается в момент
создания контейнера: обычный `up -d` без изменений в compose-файле контейнер
не пересоздаст и оставит старые переменные — со стороны выглядит как «правка
не сработала». А `down` кладёт весь стек, включая postgres и redis, ради
перечитывания одной строки.

**Звёздочку в список не добавлять** ни в каком виде — см. `assert` выше.

Если первый `grep` покажет неожиданное (два ключа сразу, значение в кавычках
целиком, перенос строки внутри списка) — скрипт упадёт на assert **до**
записи и файл останется нетронутым.

После применения — скажите, перепроверю тем же запросом с
`Origin: https://localhost` и подтвержу, что заголовок появился.

---

## Что сделано в репозитории

Не тронуты: `frontend/src/pages/*`, `App.jsx`, `main.jsx`, `server.js`,
`entry-server.jsx`, `vite.config.js`, существующие скрипты `package.json`,
`ci.yml`.

| Файл | Что |
|---|---|
| `notify.py` | Захардкоженных значений больше нет: читает `TELEGRAM_BOT_TOKEN` и `TELEGRAM_SUPPORT_CHAT_ID` из `.env` в корне (окружение процесса приоритетнее файла). Переменной нет — `SystemExit` с текстом, какой именно и куда её положить. Файл остаётся вне git (`/notify.py` в `.gitignore`) |
| `.env` | Добавлены обе переменные с прежними значениями |
| `.env.example` | Обе переменные там **уже были** (строки 99–106, с комментарием) — добавлять было нечего. Дописаны три строки про нового потребителя |
| `frontend/index.mobile.html` | HTML только для webview |
| `frontend/src/main.mobile.jsx` | Версия + запрос к `/calendar/lunar` |
| `frontend/vite.config.mobile.js` | Сборка в `dist-mobile` |
| `frontend/.env.mobile` | `VITE_API_URL=https://www.aristeatime.ru/api/v1` |
| `frontend/capacitor.config.json` | `ru.aristeatime.app` / Aristea Timeline / `dist-mobile` |
| `frontend/CAPACITOR.md` | Команды, состав файлов, требования к релизу |
| `frontend/package.json` | Одна новая строка: `"build:mobile"`. Плюс три зависимости Capacitor 7.6.9 |
| `.github/workflows/mobile-build.yml` | Новый workflow |
| `.gitignore` | `frontend/dist-mobile/`, `frontend/android/`, `frontend/.capacitor/`, `capacitor.config.local.*`, `*.keystore`, `*.jks` |

---

## Решения, которые выглядят как недоделка

Ради следующего читающего — это те места, где «очевидное улучшение» сломает
работающее.

### Абсолютный URL сделан режимом сборки, а не правкой кода

`src/config.js:1` уже читает `import.meta.env.VITE_API_URL` с фолбэком на
`/api/v1`, а `src/api/client.js` **везде** строит адрес как
`` `${API_BASE}${path}` `` — исключений в файле нет. Поэтому достаточно было
задать переменную:

- `frontend/.env.mobile` содержит `VITE_API_URL`;
- `build:mobile` собирает с `--mode mobile`;
- Vite грузит `.env.mobile` **только** в этом режиме.

Веб собирается в режиме `production`, локальная разработка — в
`development`, SSR идёт через `server.js` и `entry-server.jsx`. Ни один из
них этот файл не видит. **Это гарантия по построению, а не по
аккуратности:** появление здесь новой переменной физически не может изменить
поведение веб-сборки. Проверено прогоном `npm run build` — 0 вхождений
абсолютного URL в `dist`.

⚠️ **Что здесь важно знать на будущее:** `authFetch(url)` в `client.js` берёт
URL от вызывающего, и страницы передают туда захардкоженный `/api/v1/...` —
таких мест 30+ (`AdminPage.jsx`, `CRMPage.jsx`, `ProfilePage.jsx`,
`hooks/useExpertMode.js`, `push.js`). В каркасе это не используется, но
**настоящее мобильное приложение на них наткнётся**, и это отдельная работа,
затрагивающая файлы, которые в этом задании править было запрещено.

### `.env.mobile` закоммичен вопреки правилу `.env.*`

Секретов в нём нет — один публичный адрес API, — а CI обязан собрать бандл
без дополнительных настроек репозитория. Без файла сборка молча уйдёт на
относительный `/api/v1`, то есть на неработающую сеть. Исключение сделано
явной строкой `!frontend/.env.mobile` в `.gitignore` с комментарием, а не
разовым `git add -f`: иначе следующий человек не поймёт, почему файл в
индексе.

### Переименование `index.mobile.html` → `index.html`

Rollup именует выходной HTML по имени входного, и на диск лёг бы
`dist-mobile/index.mobile.html`. Capacitor копирует `webDir` как есть и
открывает в webview **только** `index.html`. Без переименования приложение
стартует с пустого экрана, и причина по логам не видна. Делает плагин
`mobileHtmlAsIndex` в `vite.config.mobile.js`.

### `base: './'`

Страница открывается не с сервера, а из локальных файлов APK. С абсолютного
`/assets/index-*.js` webview не найдёт ничего — снова пустой экран без
объяснений.

### Кэш Gradle отдельным шагом, а не `cache: gradle` у `setup-java`

Встроенный кэш считает ключ по gradle-файлам проекта, а их на момент
`setup-java` ещё не существует: каталог `android/` генерируется ниже, из
шаблона Capacitor. Ключ привязан к `frontend/package-lock.json` — там
зафиксирована версия Capacitor, от которой и зависит состав зависимостей
Gradle.

### Отдельный шаг-грепалка по `dist-mobile`

Проверяет ровно то, ради чего заведён отдельный режим сборки. Без неё дефект
«в бандле остался относительный `/api/v1`» доехал бы до APK и проявился уже
на устройстве — пустым экраном без диагностики, в обстановке, где отладчика
нет.

### Проверка `variables.gradle` шагом workflow

`minSdkVersion = 23` и `targetSdkVersion = 35` сегодня приходят дефолтами
Capacitor 7.6.9, руками не прописаны. Обновление Capacitor может их
сдвинуть; порог RuStore — `targetSdk` не ниже 28. Шаг падает раньше, чем
такая сборка уедет в стор.

### Отдельный конфиг Vite вместо флага в общем

Любое ветвление внутри `vite.config.js` — это ровно то место, где однажды
протечёт мобильная настройка в прод фронтенда.

---

## ⚠️ `frontend/android/` не в git — к этому придётся вернуться

CI генерирует каталог заново каждым прогоном (`npx cap add android`). Пока
правок нативной части нет, это удобно: сгенерированный Gradle-проект не лежит
в репозитории.

**Как только понадобится тронуть нативную часть — иконка, splash-экран,
разрешения, `AndroidManifest.xml` — эти правки будет стирать каждая
сборка.** Возвращаемся к этому одним из двух способов: либо коммитим
`android/` целиком и убираем генерацию из CI, либо оставляем генерацию, а все
правки держим в `capacitor.config.json` и скрипте-патчере, который CI
прогоняет после `cap add`. Первое проще и привычнее, второе не тащит в git
100+ сгенерированных файлов. Решение отложено сознательно, не «забыли».

Продублировано в `frontend/CAPACITOR.md`, чтобы нашлось на месте.

---

## Релизная подпись — в этом задании не делалась

Keystore не создавался и в репозиторий ничего не клалось. Debug-APK
подписан отладочным ключом Android SDK и годится только для установки
вручную.

Для релиза в RuStore понадобится:

1. **Keystore — создаёте вы, локально.** В репозиторий он не попадает
   никогда: по нему подписываются все будущие обновления, и потеря ключа
   означает невозможность обновить уже установленное приложение.
   ```
   keytool -genkey -v -keystore astrea-release.jks -keyalg RSA -keysize 4096 -validity 10000 -alias astrea
   ```
   Файл и пароли — во внешнее надёжное хранилище, не одной копией на этой
   машине. Риск того же класса, что и ключ от бэкапов (CLAUDE.md, «Бэкапы»).
2. **Четыре секрета репозитория** (Settings → Secrets → Actions):
   `ANDROID_KEYSTORE_BASE64`, `ANDROID_KEYSTORE_PASSWORD`,
   `ANDROID_KEY_ALIAS`, `ANDROID_KEY_PASSWORD`.
3. **`signingConfigs` в `android/app/build.gradle`** — а каталог
   генерируется, то есть это ровно тот случай из раздела выше, который
   придётся решить **до** релиза, а не после.
4. **`assembleRelease` / `bundleRelease`.** RuStore принимает и APK, и AAB.

Требования RuStore, уже закрытые дефолтами Capacitor 7: `targetSdkVersion 35`
(порог — не ниже 28), `minSdkVersion 23`, поддержка `arm64-v8a`. Доделывать
нечего.

---

## Мелочи

Два предупреждения в прогоне, оба косметические и общие для всего
репозитория, а не для этой ветки:

- `setup-java@v4` помечен устаревшим (актуален v5);
- Node 20 в actions форсится рантаймом на Node 24 — касается `checkout`,
  `setup-node`, `setup-java`, `cache`, `upload-artifact`.

Ничего не ломают. Не трогал: это правка `ci.yml`, то есть работа в `main`,
а ветка `mobile` туда не мержится.
