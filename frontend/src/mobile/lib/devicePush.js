/**
 * devicePush.js — регистрация устройства в FCM и приём входящих пушей.
 *
 * Зачем этот канал вообще, если есть локальные уведомления: без разрешения на
 * точный будильник Android ставит НЕточный, а он не будит устройство — ждёт,
 * пока человек сам возьмёт телефон. Для утреннего прогноза это отказ. Пуш с
 * высоким приоритетом — единственный механизм, который прошивки будят
 * намеренно. Разбор целиком — docs/HISTORY-push.md.
 *
 * ⚠️ ОБЪЕКТ ПЛАГИНА НЕ ВОЗВРАЩАЕТСЯ ИЗ async-ФУНКЦИИ И НЕ AWAIT-ИТСЯ.
 * `PushNotifications`, как и любой плагин Capacitor, — Proxy из
 * `registerPlugin`: его get-ловушка отдаёт вызов моста для ЛЮБОГО имени
 * свойства, включая `then`, то есть Proxy является thenable. Возврат такого
 * объекта из async-функции пропустил бы его через разворачивание thenable —
 * мост принял бы `then` за имя метода, а `resolve`/`reject` за его аргументы и
 * не позвал бы никогда. Получилось бы не падение, а ВЕЧНОЕ ЗАВИСАНИЕ, мимо
 * catch и мимо finally; в `Preferences` это стоило четырёх дней разбора
 * (CLAUDE.md, docs/HISTORY-mobile.md). Поэтому ниже обёртка `{ plugin }`.
 *
 * `addListener` — одно из четырёх имён, которые ловушка Proxy НЕ превращает в
 * вызов моста, поэтому слушатели безопасны сами по себе. Но добираться до них
 * всё равно только через обёртку: правило про объект плагина от этого не
 * меняется, а исключение легко забыть.
 */

import { IS_MOBILE } from '../../api/authTransport';
import { forgetDeviceToken, registerDeviceToken } from './moreApi';

/**
 * Обёртка вокруг объекта плагина — см. предупреждение в шапке файла.
 * `null` в вебе: пакет не должен попадать в веб-бандл даже отдельным чанком,
 * поэтому импорт динамический и внутри мобильной ветки.
 */
async function push() {
  if (!IS_MOBILE) return null;
  const mod = await import('@capacitor/push-notifications');
  return { plugin: mod.PushNotifications };
}

function failed(action, err) {
  // eslint-disable-next-line no-console
  console.warn(`[push] мобильный канал (${action}):`, err);
}

/** В вебе этого канала нет — там работают веб-пуши через VAPID. */
export const DEVICE_PUSH_SUPPORTED = IS_MOBILE;

/** Последний полученный токен — чтобы было что забыть при выключении. */
let lastToken = null;

export function currentDeviceToken() {
  return lastToken;
}

/**
 * Зарегистрировать устройство. Возвращает токен или null.
 *
 * ⚠️ Токен приходит НЕ из `register()`, а событием `registration`, и это не
 * стилистика API: `register()` только просит систему начать регистрацию и
 * завершается сразу. Ждать токен приходится через слушателя, поэтому здесь
 * гонка с таймером — без неё вызывающий не отличит «нет сервисов Google» от
 * «ещё не ответили», а первое на этом устройстве окончательно.
 *
 * ⚠️ Зовётся при КАЖДОМ запуске, а не однократно. FCM ротирует токен сам
 * (переустановка, очистка данных, перенос на новый телефон), и «один раз
 * зарегистрировались» означало бы, что сервер копит мёртвые записи, а человек
 * перестаёт получать уведомления без единого признака.
 */
export async function registerDevice({ timeoutMs = 15000 } = {}) {
  try {
    const api = await push();
    if (!api) return null;

    const perm = await api.plugin.checkPermissions();
    if (perm?.receive !== 'granted') {
      const asked = await api.plugin.requestPermissions();
      if (asked?.receive !== 'granted') return null;
    }

    const token = await new Promise((resolve) => {
      let done = false;
      const finish = (value) => {
        if (done) return;
        done = true;
        resolve(value);
      };

      // ⚠️ Ошибку регистрации глотать нельзя: она и есть признак устройства
      // без сервисов Google, на котором единственный рабочий канал —
      // локальные уведомления. Молчание здесь выглядело бы как «канал есть,
      // просто ничего не приходит».
      api.plugin.addListener('registration', (t) => finish(t?.value || null));
      api.plugin.addListener('registrationError', (err) => {
        failed('регистрация отклонена устройством', err);
        finish(null);
      });

      api.plugin.register().catch((err) => {
        failed('register', err);
        finish(null);
      });

      setTimeout(() => finish(null), timeoutMs);
    });

    if (!token) return null;

    lastToken = token;
    await registerDeviceToken(token);
    return token;
  } catch (err) {
    failed('регистрация', err);
    return null;
  }
}

/** Отвязать устройство — при выключении тумблера и при выходе из аккаунта. */
export async function unregisterDevice() {
  const token = lastToken;
  lastToken = null;
  if (!token) return;
  try {
    await forgetDeviceToken(token);
  } catch (err) {
    failed('отвязка', err);
  }
}

/**
 * Подписаться на входящие пуши.
 *
 * ⚠️ Когда приложение в ФОНЕ, уведомление показывает система, и этот код не
 * выполняется вовсе — сработает только `pushNotificationActionPerformed`, и
 * только если человек по уведомлению постучал. Это осознанная цена обычного
 * (не «молчаливого») сообщения: молчаливые будят приложение и дают полный
 * контроль, но доставляются хуже и на части прошивок режутся, а мы сюда
 * пришли именно за надёжностью доставки.
 *
 * Практическое следствие: `onKeys` — СЕТКА, а не механизм. Настоящий дедуп
 * между каналами делается выбором канала (устройство с токеном FCM своих
 * локальных уведомлений не планирует), см. docs/HISTORY-push.md.
 *
 * ⚠️ Гашение локального уведомления по ключам здесь НЕ вызывается: кода
 * локальных уведомлений на этой ветке нет вовсе, он в `local-notifications`.
 * Обработчик передан параметром именно поэтому — при слиянии веток он
 * получает реализацию, и трогать этот файл не придётся.
 */
export async function listenForPushes({ onKeys } = {}) {
  try {
    const api = await push();
    if (!api) return;

    api.plugin.addListener('pushNotificationReceived', (notification) => {
      const raw = notification?.data?.keys || '';
      const keys = raw.split(',').filter(Boolean);
      if (keys.length && typeof onKeys === 'function') onKeys(keys);
    });
  } catch (err) {
    failed('подписка на входящие', err);
  }
}
