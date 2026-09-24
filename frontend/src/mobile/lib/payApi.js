/**
 * payApi.js — оплата прямо из приложения (решение владельца 24.09.2026).
 *
 * Раньше приложение открывало веб-страницу тарифов во внешнем браузере. У
 * браузера своя сессия: человеку приходилось входить на сайте заново, и вход
 * другим аккаунтом означал «заплатила, а покупки нет». Теперь платёж создаёт
 * само приложение своим входом (`POST /payments/checkout`, `source: 'app'`) и
 * открывает во внешнем браузере уже страницу ЮKassa — аккаунт тот же по
 * построению, а номер платежа приложение знает и может спросить его статус.
 *
 * Правило RuStore, по которому это можно, — CLAUDE.md, раздел «Из
 * мобильного приложения можно вести на веб-оплату».
 */

import { API_BASE } from '../../config';
import { responseErrorText } from '../../api/client';
import { authFetchWithTimeout, failWith, getWithRetry } from './authFetchTimeout';

const PENDING_KEY = 'aristea_pending_payment';
/** Дольше суток ожидание не показываем: ЮKassa к этому времени платёж давно решила. */
export const PENDING_TTL_MS = 24 * 60 * 60 * 1000;

export async function createAppCheckout(tier) {
  const resp = await authFetchWithTimeout(`${API_BASE}/payments/checkout`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tier, billing_period: 'monthly', source: 'app' }),
  });
  if (!resp.ok) throw new Error(await responseErrorText(resp, 'Не удалось начать оплату.'));
  return resp.json();   // { checkout_url, payment_id }
}

export async function fetchPaymentStatus(paymentId) {
  const resp = await getWithRetry(`${API_BASE}/payments/status/${encodeURIComponent(paymentId)}`);
  if (!resp.ok) await failWith(resp, 'Не удалось проверить оплату.');
  return resp.json();
}

export async function fetchPaymentHistory() {
  const resp = await getWithRetry(`${API_BASE}/payments/history`);
  if (!resp.ok) await failWith(resp, 'Не удалось загрузить платежи.');
  return resp.json();
}

/** Сообщение в поддержку — тот же канал, что жалобы (`POST /feedback`). */
export async function sendSupportMessage(message) {
  const form = new FormData();
  form.append('screen', 'payment');
  form.append('message', message);
  form.append('user_agent', typeof navigator !== 'undefined' ? navigator.userAgent : '');
  const resp = await authFetchWithTimeout(`${API_BASE}/feedback`, { method: 'POST', body: form });
  if (!resp.ok) throw new Error(await responseErrorText(resp, 'Не удалось отправить сообщение.'));
  return resp.json();
}

// ── Ожидающий платёж ──────────────────────────────────────
// Хранится на устройстве, чтобы экран ожидания пережил уход в браузер,
// выгрузку приложения системой и перезапуск. localStorage, а не Preferences:
// потеря записи безопасна — тариф всё равно включит вебхук или сверка.

export function rememberPending(paymentId, tier, now = Date.now()) {
  try { localStorage.setItem(PENDING_KEY, JSON.stringify({ id: paymentId, tier, at: now })); } catch { /* только память */ }
}

export function readPending(now = Date.now()) {
  try {
    const p = JSON.parse(localStorage.getItem(PENDING_KEY) || 'null');
    if (p?.id && now - p.at < PENDING_TTL_MS) return p;
  } catch { /* битая запись — как нет */ }
  return null;
}

export function clearPending() {
  try { localStorage.removeItem(PENDING_KEY); } catch { /* нечего */ }
}
