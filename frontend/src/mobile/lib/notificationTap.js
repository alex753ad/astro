/**
 * notificationTap.js — куда вести человека, постучавшего по уведомлению.
 *
 * До 23.09.2026 нажатие не обрабатывалось вовсе: приложение просто
 * открывалось, а `url` в данных уведомления никто не читал. Для приложения
 * сервер теперь кладёт отдельное поле `target` (у ежедневного — "feed_today");
 * `url` остаётся вебу и здесь не используется (решение владельца 23.09.2026).
 *
 * Два канала — два места, где лежит target:
 *   FCM (`pushNotificationActionPerformed`) — `notification.data.target`;
 *   локальные (`localNotificationActionPerformed`) — `notification.extra.target`.
 *
 * ⚠️ Объект плагина — только через обёртку `{ plugin }`, не возвращать и не
 * await-ить (CLAUDE.md, раздел про Capacitor): `addListener` сам по себе
 * безопасен, но правило про Proxy от этого не меняется.
 */

import { IS_MOBILE } from '../../api/authTransport';

// feed_today — утреннее «прогноз дня», feed_tomorrow — вечернее «прогноз на
// завтра» (с 24.09.2026): открыть ленту и развернуть карточку своего дня.
export const KNOWN_TARGETS = new Set(['feed_today', 'feed_tomorrow']);

/** Разобрать target из события нажатия любого из двух каналов. */
export function targetOfAction(action) {
  const n = action?.notification;
  const raw = n?.data?.target || n?.extra?.target || '';
  return KNOWN_TARGETS.has(raw) ? raw : null;
}

async function plugins() {
  if (!IS_MOBILE) return null;
  const [local, push] = await Promise.all([
    import('@capacitor/local-notifications').catch(() => null),
    import('@capacitor/push-notifications').catch(() => null),
  ]);
  return { local: local?.LocalNotifications || null, push: push?.PushNotifications || null };
}

/**
 * Подписаться на нажатия. `onTarget(target)` зовётся только с известным target.
 * Возвращает функцию отписки.
 */
export async function listenForTaps(onTarget) {
  const handles = [];
  try {
    const api = await plugins();
    if (!api) return () => {};
    const handler = (action) => {
      const target = targetOfAction(action);
      if (target) onTarget(target);
    };
    if (api.local) handles.push(await api.local.addListener('localNotificationActionPerformed', handler));
    if (api.push) handles.push(await api.push.addListener('pushNotificationActionPerformed', handler));
  } catch (err) {
    // eslint-disable-next-line no-console
    console.warn('[push] подписка на нажатия:', err);
  }
  return () => handles.forEach((h) => h?.remove?.());
}
