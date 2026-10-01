/**
 * firstWeek.js — первая неделя по сценарию (флаг first_week).
 *
 * Правило «какой день, что подсвечивать» живёт на сервере
 * (backend/first_week.py) — здесь только запрос карточки и отметки «открыл».
 * Отметку шлют сами экраны в момент, когда человек открыл функцию (карта,
 * прогноз, разбор, разбор транзита, период, чат, итог): по ней карточка
 * пропадает, а вечерний пуш этого дня не уходит.
 *
 * ⚠️ Флаг выключен — ни одного запроса: отметка зовётся из экранов, которые
 * открывают все, и без проверки каждое открытие карты било бы в 404.
 */
import { API_BASE } from '../../config';
import { authFetch } from '../../api/client';
import { isFlagOn } from '../../lib/flags';

export const FIRST_WEEK_FLAG = 'first_week';
/** Отметка ушла — карточка перезапрашивается. */
export const FIRST_WEEK_EVENT = 'aristea:first-week';
/** Кнопка карточки «чат» — открыть чат (слушает AristeaFab). */
export const OPEN_CHAT_EVENT = 'aristea:open-chat';
/** Кнопка карточки «разбор карты» — открыть разбор (слушает ChartScreen). */
export const OPEN_INTERPRET_EVENT = 'aristea:open-interpret';

const sent = new Set(); // отмеченное за запуск: повторно не шлём

export function emit(name) {
  try { window.dispatchEvent(new Event(name)); } catch { /* не браузер */ }
}

export async function fetchFirstWeek() {
  const r = await authFetch(`${API_BASE}/first-week`);
  if (!r.ok) return null;
  return (await r.json())?.card || null;
}

export function markSeen(key) {
  if (!isFlagOn(FIRST_WEEK_FLAG) || sent.has(key)) return;
  sent.add(key);
  authFetch(`${API_BASE}/first-week/seen`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ key }),
  })
    .then((r) => { if (r.ok) emit(FIRST_WEEK_EVENT); else sent.delete(key); })
    .catch(() => sent.delete(key));
}
