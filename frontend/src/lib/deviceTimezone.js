/**
 * deviceTimezone.js — пояс телефона (в вебе — браузера) для сервера.
 *
 * Решение владельца 24.09.2026: лента, планер, прогноз и уведомления
 * показывают время в поясе УСТРОЙСТВА; пояс карты (места рождения) — только
 * запасной, если устройство пояса не прислало. Общий файл веба и приложения.
 *
 * Два пути доставки, и оба нужны:
 *   • `withTz(url)` — параметр `tz` у запросов ленты, планера, прогноза и
 *     `/push/upcoming`: ответ сразу в нужном поясе;
 *   • `syncDeviceTimezone()` — `PATCH /push/settings {timezone}`: сервер
 *     помнит пояс для уведомлений, которые он шлёт САМ по расписанию, когда
 *     никакого запроса от устройства нет.
 */

export function deviceTimeZone() {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || '';
  } catch {
    return '';
  }
}

export function withTz(url, tz = deviceTimeZone()) {
  return tz ? `${url}${url.includes('?') ? '&' : '?'}tz=${encodeURIComponent(tz)}` : url;
}

const SENT_KEY = 'aristea_device_tz_sent';

/**
 * Сообщить серверу пояс, если он изменился с прошлого раза для этого
 * пользователя. `patch(body)` — вызов `PATCH /push/settings` с авторизацией;
 * отдаётся снаружи, чтобы файл не тянул транспорт. Ошибки глотаются: пояс
 * пришлём при следующем входе, а пока сервер считает по поясу карты.
 */
export async function syncDeviceTimezone(userId, patch, tz = deviceTimeZone()) {
  if (!userId || !tz) return false;
  const mark = `${userId}:${tz}`;
  try {
    if (localStorage.getItem(SENT_KEY) === mark) return false;
  } catch { /* без хранилища — просто шлём */ }
  try {
    const ok = await patch({ timezone: tz });
    if (!ok) return false;
    try { localStorage.setItem(SENT_KEY, mark); } catch { /* повторим в следующий раз */ }
    return true;
  } catch {
    return false;
  }
}
