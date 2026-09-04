# Мобильная сборка (Capacitor / Android)

Каркас сборки. Экранов приложения здесь нет — первая сборка показывает версию
и результат одного запроса к боевому API, чем доказывает, что цепочка
`vite → dist-mobile → cap sync → APK → webview` работает и что из webview
проходит сеть.

## Как собрать APK

Локально ничего для Android ставить не нужно — сборка идёт в CI:

- вручную: вкладка **Actions → Mobile APK → Run workflow** (ветка `mobile`);
- автоматически: любой push в ветку `mobile`;
- APK лежит в артефактах прогона под именем `astrea-debug-apk`.

Из командной строки:

```
gh workflow run mobile-build.yml --ref mobile
gh run watch
gh run download <RUN_ID> -n astrea-debug-apk
```

Локально (если однажды появится JDK 21 + Android SDK):

```
cd frontend
npm ci
npm run build:mobile
npx cap add android      # только если каталога android/ ещё нет
npx cap sync android
cd android && ./gradlew assembleDebug
```

## Что где лежит

| Файл | Роль |
|---|---|
| `index.mobile.html` | HTML только для webview: без PWA-манифеста и без внешних шрифтов |
| `src/main.mobile.jsx` | Точка входа: версия + проверка сети через `/calendar/lunar` |
| `vite.config.mobile.js` | Сборка в `dist-mobile`, `base: './'`, переименование HTML в `index.html` |
| `.env.mobile` | `VITE_API_URL` — абсолютный адрес боевого API, читается только при `--mode mobile` |
| `capacitor.config.json` | appId `ru.aristeatime.app`, webDir `dist-mobile` |

Веб-сборка, SSR (`server.js`, `src/entry-server.jsx`) и локальная разработка
не затронуты: у мобильной сборки отдельный конфиг и отдельный режим Vite.

## android/ не в git — и это временно

`frontend/android/` в `.gitignore`, CI генерирует каталог заново каждым
прогоном через `npx cap add android`. Пока правок нативной части нет, это
удобно: в репозитории не лежит сгенерированный Gradle-проект.

⚠️ **Как только понадобится тронуть нативную часть — иконка, splash-экран,
разрешения в `AndroidManifest.xml`, имя приложения на разных локалях, —
правки будут стираться каждой сборкой.** Возвращаться к этому надо будет
одним из двух способов: либо закоммитить `android/` целиком и убрать
генерацию из CI, либо оставить генерацию, а все правки держать в
`capacitor.config.json` и скрипте-патчере, который CI прогоняет после
`cap add`. Первое проще и привычнее, второе не тащит в git 100+
сгенерированных файлов. Решение отложено сознательно, не «забыли».

## Что нужно для релизной сборки (в этом задании не делалось)

Debug-APK подписывается автоматически отладочным ключом Android SDK и годится
только для установки вручную. Для RuStore нужен release, и для него понадобится:

1. **Keystore.** Создаёте вы, локально, и в репозиторий он не попадает
   никогда — по нему подписываются все будущие обновления, и потеря ключа
   означает невозможность обновить уже установленное приложение:
   `keytool -genkey -v -keystore astrea-release.jks -keyalg RSA -keysize 4096 -validity 10000 -alias astrea`
   Файл и пароли — во внешнее надёжное хранилище, не на этой машине одной копией.
2. **Четыре секрета репозитория** (Settings → Secrets → Actions):
   `ANDROID_KEYSTORE_BASE64` (файл в base64), `ANDROID_KEYSTORE_PASSWORD`,
   `ANDROID_KEY_ALIAS`, `ANDROID_KEY_PASSWORD`.
3. **`signingConfigs` в `android/app/build.gradle`** — а поскольку каталог
   генерируется, это ровно тот случай из раздела выше, который придётся решать
   до релиза, а не после.
4. **`assembleRelease` / `bundleRelease`.** RuStore принимает и APK, и AAB.
5. **Требования RuStore**, которые уже выполнены Capacitor 7 по умолчанию:
   `minSdkVersion 23`, `targetSdkVersion 35` (порог RuStore — не ниже 28),
   `compileSdk 35`; `arm64-v8a` поддержан, так как `abiFilters` не задан и
   нативных библиотек своей сборки у проекта нет.
