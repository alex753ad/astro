/**
 * deviceChannel.js — включение канала уведомлений на устройстве: намерение
 * человека (флаг тумблера) и выбор канала. Общее для тумблера в «Ещё»
 * (MoreDeviceChannel.jsx) и экрана первого запуска (PushNudge.jsx), чтобы
 * правило «ровно один канал» жило в одном месте. Почему канал выбирается
 * так — шапка MoreDeviceChannel.jsx.
 */

import { registerDevice } from './devicePush';
import { cancelOwnedPlan, permissionState } from './localNotifications';
import { CHANNEL_DEVICE, CHANNEL_SERVER, decideChannel } from './channelChoice';
import { setLocalNotificationsEnabled, syncLocalNotifications } from './localNotificationsSync';

/** Намерение человека — отдельно от системного разрешения и от наличия токена. */
const ENABLED_KEY = 'aristea_device_push';

/**
 * null — человек тумблер не трогал ни разу; '1' / '0' — включил / выключил.
 * ⚠️ null и '0' различаются намеренно: экран первого запуска (pushNudge.js)
 * не спрашивает того, кто выключил уведомления сам.
 */
export function deviceChoice() {
  try {
    return localStorage.getItem(ENABLED_KEY);
  } catch {
    return null;
  }
}

export function devicePushEnabled() {
  return deviceChoice() === '1';
}

export function setDevicePushEnabled(on) {
  try {
    localStorage.setItem(ENABLED_KEY, on ? '1' : '0');
  } catch {
    /* приватный режим webview — тумблер просто не запомнится */
  }
}

/**
 * Включить канал: сначала серверный, при неудаче — локальный. Спрашивает
 * системное разрешение, если его нет (внутри registerDevice). Возвращает
 * выбранный канал или null.
 *
 * ⚠️ Порядок обязателен и не взаимозаменяем. Серверный будит устройство,
 * локальный нет; выбрать локальный там, где работает серверный, значит
 * сознательно отдать человеку худший канал. Поэтому локальный включается
 * ТОЛЬКО как ответ на неудачу регистрации.
 */
export async function chooseChannel() {
  const token = await registerDevice();
  // ⚠️ Решение — в `channelChoice.js`, отдельной чистой функцией, и это не
  // церемония: инвариант «активен ровно один канал» внутри обработчика
  // нечем закрепить, кроме рендера, а цена его нарушения — дубли в шторке.
  // Здесь остаются только последствия решения.
  const chosen = decideChannel(token, await permissionState());

  if (chosen === CHANNEL_SERVER) {
    // Серверный канал работает. Локальные обязаны замолчать — иначе одно и
    // то же событие придёт дважды: пушем и своим уведомлением.
    setLocalNotificationsEnabled(false);
    await cancelOwnedPlan();
    return chosen;
  }

  if (chosen === CHANNEL_DEVICE) {
    // ⚠️ Сюда приходит устройство БЕЗ сервисов Google: у него регистрация не
    // удастся никогда, и локальные уведомления — единственное, что у него
    // вообще может работать. Разрешение уже выдано (его спрашивает
    // registerDevice до обращения к серверу), второй раз не спрашиваем.
    setLocalNotificationsEnabled(true);
    await syncLocalNotifications();
    return chosen;
  }
  return null;
}

/** Включить и запомнить намерение — то же, что «Разрешить» у тумблера. */
export async function enableDeviceChannel() {
  const chosen = await chooseChannel();
  if (chosen) setDevicePushEnabled(true);
  return chosen;
}
