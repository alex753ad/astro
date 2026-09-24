/**
 * webPayment.js — номер платежа, ушедшего на страницу ЮKassa с веба.
 *
 * ЮKassa возвращает на `/payment/return` без номера платежа в адресе (адрес
 * возврата задаётся ДО создания платежа, номер тогда ещё неизвестен). Поэтому
 * номер кладётся сюда перед уходом, а страница возврата его читает и
 * спрашивает статус. Потеря записи безопасна: тариф всё равно включат вебхук
 * или ежедневная сверка, страница просто скажет «проверим сами».
 */

const KEY = 'aristea_web_payment';

export function rememberWebPayment(paymentId, tier) {
  if (!paymentId) return;
  try { localStorage.setItem(KEY, JSON.stringify({ id: paymentId, tier, at: Date.now() })); } catch { /* нечего */ }
}

export function readWebPayment() {
  try { return JSON.parse(localStorage.getItem(KEY) || 'null'); } catch { return null; }
}

export function clearWebPayment() {
  try { localStorage.removeItem(KEY); } catch { /* нечего */ }
}
