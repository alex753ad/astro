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

export const fetchMe = () => getJson('/auth/me', 'Не удалось загрузить профиль.');

export const fetchSubscription = () => getJson('/profile/subscription', 'Не удалось загрузить тариф.');

/** `{ total, offset, limit, primary_chart_id, charts: [...] }` — весь объект, не только массив: список карт (§5) читает `primary_chart_id` из корня. */
export const fetchCharts = () => getJson('/profile/charts', 'Не удалось загрузить карты.');

export const fetchHistory = () => getJson('/profile/history', 'Не удалось загрузить историю разборов.');

export const fetchReferral = () => getJson('/profile/referral', 'Не удалось загрузить реферальную ссылку.');

export const fetchPushSettings = () => getJson('/push/settings', 'Не удалось загрузить настройки уведомлений.');
export const updatePushSettings = (patch) => patchJson('/push/settings', patch, 'Не удалось сохранить настройки уведомлений.');

export const fetchProfileSettings = () => getJson('/profile/settings', 'Не удалось загрузить настройки.');
export const updateProfileSettings = (patch) => patchJson('/profile/settings', patch, 'Не удалось сохранить настройки.');
