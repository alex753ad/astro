/**
 * moreApi.js — запросы экрана «Ещё» (SPEC_MORE_SCREEN.md §2).
 *
 * Три при открытии (`fetchMe`, `fetchSubscription`, `fetchCharts`) —
 * параллельно, без зависимости друг от друга. Остальные четыре — только по
 * тапу на соответствующий пункт меню, не при открытии экрана.
 *
 * `GET /profile/export` здесь нет: в мобильном приложении выгрузки данных
 * не будет (SPEC_MORE_SCREEN.md §6.2) — четыре способа рассмотрены и
 * отклонены, ссылка на веб-кабинет собирается прямо в MoreScreen.jsx.
 */

import { API_BASE } from '../../config';
import { responseErrorText } from '../../api/client';
import { authFetchWithTimeout } from './authFetchTimeout';

async function getJson(path, fallback) {
  const resp = await authFetchWithTimeout(`${API_BASE}${path}`);
  if (!resp.ok) throw new Error(await responseErrorText(resp, fallback));
  return resp.json();
}

async function patchJson(path, body, fallback) {
  const resp = await authFetchWithTimeout(`${API_BASE}${path}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw new Error(await responseErrorText(resp, fallback));
  return resp.json();
}

async function postJson(path, body, fallback) {
  const resp = await authFetchWithTimeout(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw new Error(await responseErrorText(resp, fallback));
  return resp.json();
}

export const fetchMe = () => getJson('/auth/me', 'Не удалось загрузить профиль.');

export const fetchSubscription = () => getJson('/profile/subscription', 'Не удалось загрузить тариф.');

/** `{ total, offset, limit, primary_chart_id, charts: [...] }` — весь объект, не только массив: список карт (§5) читает `primary_chart_id` из корня. */
export const fetchCharts = () => getJson('/profile/charts', 'Не удалось загрузить карты.');

export const fetchHistory = () => getJson('/profile/history', 'Не удалось загрузить историю разборов.');

export const fetchReferral = () => getJson('/profile/referral', 'Не удалось загрузить реферальную ссылку.');

export const fetchPushSettings = () => getJson('/push/settings', 'Не удалось загрузить настройки уведомлений.');
export const updatePushSettings = (patch) => patchJson('/push/settings', patch, 'Не удалось сохранить настройки уведомлений.');

/**
 * Будущие события для локальных уведомлений — `GET /push/upcoming`.
 *
 * Отдаёт `{ timezone, days, events: [{ key, kind, at, title, body, url }] }`
 * с ГОТОВЫМИ формулировками: критерий отбора и тексты живут на бэкенде в одном
 * экземпляре (backend/push/cron.py, collect_upcoming). Клиенту остаётся
 * склеить список и поставить — сочинять свой текст нельзя.
 */
export const fetchUpcomingNotifications = () =>
  getJson('/push/upcoming', 'Не удалось загрузить будущие события.');

/**
 * Токен устройства для мобильных пушей — `POST/DELETE /push/device`.
 *
 * Токен шлётся при каждом запуске, а не однократно: FCM ротирует его сам, и
 * сервер обязан узнать новый, иначе уведомления тихо перестанут приходить.
 * Повторный вызов с тем же токеном ничего не меняет, кроме отметки времени.
 */
export const registerDeviceToken = (token) =>
  postJson('/push/device', { token, platform: 'android' }, 'Не удалось зарегистрировать устройство.');

export async function forgetDeviceToken(token) {
  const resp = await authFetchWithTimeout(`${API_BASE}/push/device`, {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token, platform: 'android' }),
  });
  if (!resp.ok) throw new Error(await responseErrorText(resp, 'Не удалось отвязать устройство.'));
}

export const fetchProfileSettings = () => getJson('/profile/settings', 'Не удалось загрузить настройки.');
export const updateProfileSettings = (patch) => patchJson('/profile/settings', patch, 'Не удалось сохранить настройки.');

/**
 * Удаление карты — `DELETE /profile/charts/{id}` (`profile/router.py:157`).
 *
 * Возврата нет: список правится на месте тем, кто вызвал. Перезапрашивать
 * `/profile/charts` не нужно — состав известен, а лишний запрос на экране,
 * который и так делает три при открытии, ничего не уточняет.
 *
 * ⚠️ Если удалена основная карта, `primary_chart_id` сбрасывает САМ БЭКЕНД
 * (там же, строки 180-181) — клиенту чинить состояние не нужно и нельзя:
 * своя «догадка» о новой основной разошлась бы с серверной.
 */
export async function deleteChart(chartId) {
  const resp = await authFetchWithTimeout(`${API_BASE}/profile/charts/${chartId}`, { method: 'DELETE' });
  if (!resp.ok) {
    throw new Error(await responseErrorText(resp, 'Не удалось удалить карту.'));
  }
}

/** Закрепление основной карты — `PATCH /profile/primary-chart`. */
export const setPrimaryChart = (chartId) =>
  patchJson('/profile/primary-chart', { chart_id: chartId }, 'Не удалось сделать карту основной.');
