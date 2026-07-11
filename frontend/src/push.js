/**
 * Web Push helper.
 *
 * enablePush(authFetch)  — спросить разрешение, подписаться, отправить подписку на бэк
 * disablePush(authFetch) — отписаться и удалить подписку на бэке
 * pushSupported()        — поддерживает ли браузер push
 *
 * Service Worker уже регистрируется в index.html (/sw.js).
 */

const API_BASE = '/api/v1';

function urlBase64ToUint8Array(base64String) {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
  const raw = atob(base64);
  const out = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
  return out;
}

export function pushSupported() {
  return (
    typeof navigator !== 'undefined' &&
    'serviceWorker' in navigator &&
    'PushManager' in window &&
    'Notification' in window
  );
}

/** Спросить разрешение, подписаться на push и сохранить подписку на сервере. */
export async function enablePush(authFetch) {
  if (!pushSupported()) throw new Error('Браузер не поддерживает push-уведомления');

  const permission = await Notification.requestPermission();
  if (permission !== 'granted') {
    throw new Error('Разрешение на уведомления не выдано');
  }

  const reg = await navigator.serviceWorker.ready;
  let sub = await reg.pushManager.getSubscription();

  if (!sub) {
    const { public_key } = await authFetch(`${API_BASE}/push/vapid-public-key`);
    sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(public_key),
    });
  }

  const json = sub.toJSON();
  await authFetch(`${API_BASE}/push/subscribe`, {
    method: 'POST',
    body: JSON.stringify({ endpoint: json.endpoint, keys: json.keys }),
  });

  return true;
}

/** Отписаться от push и удалить подписку на сервере. */
export async function disablePush(authFetch) {
  if (!pushSupported()) return;
  const reg = await navigator.serviceWorker.ready;
  const sub = await reg.pushManager.getSubscription();
  if (!sub) return;
  try {
    await authFetch(`${API_BASE}/push/unsubscribe`, {
      method: 'POST',
      body: JSON.stringify({ endpoint: sub.endpoint }),
    });
  } catch (_) { /* игнорируем — всё равно отписываемся локально */ }
  await sub.unsubscribe();
}
