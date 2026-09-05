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

if (failed) {
  console.error('patch-android: правки не применены — сборка остановлена');
  process.exit(1);
}
console.log('patch-android: готово');
