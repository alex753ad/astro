/**
 * supportBus.js — «написать в поддержку» из любого места приложения.
 *
 * Лист поддержки один и живёт в TabShell (как лист оплаты, paySheetBus.js);
 * меню «Ещё», оплата и экраны ошибок только просят его открыться и говорят,
 * откуда: `screen` — где человек был, `error` — текст ошибки, которую он видел.
 */

import { API_BASE } from '../../config';
import { authFetchWithTimeout, failWith } from './authFetchTimeout';
import { appVersionLabel, deviceLabel, scrubErrorText } from './supportContext';

const listeners = new Set();

/** @param {{screen?: string, error?: string}} [opts] */
export function openSupport(opts = {}) {
  for (const fn of [...listeners]) fn(opts);
}

export function onSupport(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

/**
 * Обращение — тот же канал, что жалобы (`POST /feedback` → Telegram
 * владельцу). Номер аккаунта и email сервер берёт из токена; у экрана
 * `payment` сам приклеивает тариф и платежи.
 */
export async function sendSupportMessage({ message, screen, error }) {
  const form = new FormData();
  form.append('screen', screen || 'support');
  form.append('message', message);
  form.append('app_version', appVersionLabel());
  form.append('device', deviceLabel());
  const err = scrubErrorText(error);
  if (err) form.append('error_text', err);
  form.append('user_agent', typeof navigator !== 'undefined' ? navigator.userAgent : '');
  const resp = await authFetchWithTimeout(`${API_BASE}/feedback`, { method: 'POST', body: form });
  if (!resp.ok) await failWith(resp, 'Не удалось отправить сообщение.');
  return resp.json();
}
