/**
 * patch-android.mjs — правки нативного проекта, который генерируется заново.
 *
 * Каталог frontend/android/ не в git: CI создаёт его каждым прогоном через
 * `npx cap add android`. Значит любая правка руками стирается следующей
 * сборкой, и держать её можно только скриптом, который прогоняется ПОСЛЕ
 * генерации. Это и есть тот «скрипт-патчер» из frontend/CAPACITOR.md.
 *
 * Скрипт идемпотентен: повторный запуск на уже пропатченном проекте ничего не
 * делает и завершается успешно — иначе он ломал бы локальную сборку, где
 * android/ переживает несколько прогонов.
 *
 * Каждая правка обязана найти свой якорь. Не нашла — падаем с ненулевым кодом,
 * а не пропускаем молча: молчаливый пропуск здесь означает APK, собранный без
 * правки, о которой все думают, что она есть. Ровно так теряются настройки
 * безопасности при апгрейде Capacitor, меняющем шаблон.
 *
 * Запуск: node scripts/patch-android.mjs   (из каталога frontend)
 */

import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const MANIFEST = path.join(root, 'android', 'app', 'src', 'main', 'AndroidManifest.xml');

let failed = false;

function patch({ file, name, anchor, replacement, doneWhen }) {
  if (!existsSync(file)) {
    console.error(`✗ ${name}: файла нет — ${file}`);
    failed = true;
    return;
  }
  const text = readFileSync(file, 'utf-8');

  if (doneWhen(text)) {
    console.log(`· ${name}: уже применено`);
    return;
  }

  const count = text.split(anchor).length - 1;
  if (count !== 1) {
    console.error(`✗ ${name}: якорь найден ${count} раз (ожидался ровно 1): ${anchor}`);
    failed = true;
    return;
  }

  const patched = text.replace(anchor, replacement);
  if (patched === text) {
    console.error(`✗ ${name}: замена не применилась`);
    failed = true;
    return;
  }

  writeFileSync(file, patched, 'utf-8');
  console.log(`✓ ${name}`);
}

/**
 * allowBackup=false.
 *
 * Шаблон Capacitor ставит true. С ним содержимое приватного каталога
 * приложения — включая нативное хранилище Preferences, где лежит refresh-токен
 * на 7 дней, — уезжает в резервные копии и вытаскивается через `adb backup`.
 * Для токена такого срока жизни это и есть основной способ утечки: песочница
 * приложения на нерутованном устройстве держит всё остальное.
 *
 * Цена: пользователь при переносе на новое устройство войдёт заново. Для
 * приложения, где вход — это одна форма, это дешевле утечки долгоживущего
 * токена.
 */
patch({
  file: MANIFEST,
  name: 'allowBackup=false',
  anchor: 'android:allowBackup="true"',
  replacement: 'android:allowBackup="false"',
  doneWhen: (t) => t.includes('android:allowBackup="false"'),
});

/**
 * screenOrientation=portrait на MainActivity.
 *
 * Экраны (форма входа, таб-бар) свёрстаны под портретную раскладку без
 * альтернативной вёрстки для альбомной. Без явного запрета поворот доступен
 * по умолчанию, и поворот планшета/телефона на бок даёт не адаптивный
 * лейаут, а обрезанные и наползающие друг на друга элементы.
 *
 * android:configChanges (уже в шаблоне, включает "orientation|screenSize")
 * этому не мешает — тот атрибут регулирует, пересоздаётся ли Activity при
 * смене конфигурации, а не то, разрешён ли сам поворот; в портретном режиме
 * событие смены ориентации просто не наступает.
 */
patch({
  file: MANIFEST,
  name: 'screenOrientation=portrait',
  anchor: 'android:launchMode="singleTask"',
  replacement: 'android:launchMode="singleTask"\n            android:screenOrientation="portrait"',
  doneWhen: (t) => t.includes('android:screenOrientation="portrait"'),
});

/**
 * windowSoftInputMode=adjustResize на MainActivity.
 *
 * Шаблон Capacitor этот атрибут не ставит вовсе — проверено грепом по всему
 * @capacitor/*, там его нет ни в одном шаблоне. Значит применяется умолчание
 * Android (SOFT_INPUT_ADJUST_UNSPECIFIED), где режим выбирает система, и
 * выбор её от устройства к устройству не гарантирован.
 *
 * Приложению это стало важно с появлением чата: у него поле ввода прижато к
 * низу шторки (`position: fixed; bottom: 0`, AristeaChat.jsx). При
 * adjustResize окно ужимается по высоте, viewport вместе с ним, и поле
 * поднимается над клавиатурой само. При adjustPan окно не ужимается, а
 * сдвигается — `position: fixed` считается от НЕсдвинутого viewport, и поле
 * ввода остаётся под клавиатурой: человек печатает вслепую.
 *
 * ⚠️ Это первая мера, а не гарантия. Поведение WebView с клавиатурой
 * проверяется только на устройстве (ACCEPTANCE_CHAT.md §5). Если adjustResize
 * окажется недостаточно — следующим шагом @capacitor/keyboard, но это
 * нативный плагин, и ставится он только отдельным решением владельца, а не
 * походя: в решении назвать, что плагин даёт и чего это стоит.
 *
 * Якорь — тот же launchMode, что у портретной ориентации: оба атрибута
 * висят на одной activity. Порядок правок при этом значения не имеет, каждая
 * ищет свой якорь заново и обе идемпотентны.
 */
patch({
  file: MANIFEST,
  name: 'windowSoftInputMode=adjustResize',
  anchor: 'android:launchMode="singleTask"',
  replacement: 'android:launchMode="singleTask"\n            android:windowSoftInputMode="adjustResize"',
  doneWhen: (t) => t.includes('android:windowSoftInputMode="adjustResize"'),
});

/**
 * Разрешения локальных уведомлений в манифесте приложения.
 *
 * POST_NOTIFICATIONS нужен на Android 13+ (API 33): без него
 * `LocalNotifications.schedule` отработает без ошибки, а в шторке не появится
 * ничего — тот самый молчаливый отказ, ради которого этот скрипт и падает при
 * ненайденном якоре. На API 23-32 разрешения не существует, и там уведомления
 * управляются системным переключателем приложения; ветвление по версии делает
 * сам плагин в нативном коде (см. localNotifications.js, там же почему не мы).
 *
 * RECEIVE_BOOT_COMPLETED нужен, чтобы уведомления пережили перезагрузку
 * телефона. AlarmManager теряет все будильники при выключении; плагин хранит
 * поставленное у себя и восстанавливает по BOOT_COMPLETED
 * (`LocalNotificationRestoreReceiver`), но без этого разрешения его приёмник
 * события просто не получит — и человек перестанет получать уведомления после
 * первой же перезагрузки, ничего об этом не узнав.
 *
 * ⚠️ Это ДУБЛЬ того, что и так приезжает из манифеста самого плагина
 * (`node_modules/@capacitor/local-notifications/android/src/main/AndroidManifest.xml`
 * объявляет POST_NOTIFICATIONS, RECEIVE_BOOT_COMPLETED и WAKE_LOCK, и
 * манифесты библиотек сливаются с манифестом приложения при сборке). Дубль
 * оставлен намеренно, по двум причинам:
 *
 *   1. Разрешение, от которого зависит вся функция, объявлено там, где его
 *      будут искать, — в манифесте приложения, а не в чужом node_modules.
 *   2. Слияние манифестов — это то, что можно потерять при апгрейде плагина,
 *      не заметив: APK соберётся, уведомления перестанут показываться на
 *      Android 13+, и никакой ошибки при этом не будет. Здесь же стоит
 *      grep-проверка в mobile-build.yml, которой без явной строки не на что
 *      было бы смотреть.
 *
 * Якорь — закрывающий </manifest>, а не строка INTERNET-разрешения: генератор
 * иконки (@capacitor/assets) переформатирует манифест целиком и на расстановку
 * пробелов внутри тега полагаться нельзя, а закрывающий тег в файле ровно один
 * при любом форматировании.
 */
const NOTIFICATION_PERMISSIONS = `    <uses-permission android:name="android.permission.POST_NOTIFICATIONS" />
    <uses-permission android:name="android.permission.RECEIVE_BOOT_COMPLETED" />
</manifest>`;

patch({
  file: MANIFEST,
  name: 'разрешения уведомлений',
  anchor: '</manifest>',
  replacement: NOTIFICATION_PERMISSIONS,
  doneWhen: (t) =>
    t.includes('android.permission.POST_NOTIFICATIONS') &&
    t.includes('android.permission.RECEIVE_BOOT_COMPLETED'),
});

if (failed) {
  console.error('patch-android: правки не применены — сборка остановлена');
  process.exit(1);
}
console.log('patch-android: готово');
