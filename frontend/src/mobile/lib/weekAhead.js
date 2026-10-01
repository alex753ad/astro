/**
 * weekAhead.js — «Неделя вперёд» (флаг week_ahead).
 *
 * Когда показывать и какие события — решает сервер (backend/week_ahead.py):
 * с воскресенья 19:00 до конца понедельника, иначе card = null.
 */
import { API_BASE } from '../../config';
import { authFetch } from '../../api/client';

export const WEEK_AHEAD_FLAG = 'week_ahead';

export async function fetchWeekAhead() {
  const r = await authFetch(`${API_BASE}/week-ahead`);
  if (!r.ok) return null;
  return (await r.json())?.card || null;
}

/**
 * Событие ленты для строки карточки: транзит того же дня с теми же
 * планетами и аспектом. Нет (Луна, фаза, событие вне окна ленты) — null,
 * и лента просто доезжает до дня.
 */
export function findFeedEvent(events, row) {
  if (!row?.natal) return null;
  return (events || []).find((e) => e.kind === 'transit'
    && e.at?.slice(0, 10) === row.date
    && e.meta?.transit_planet === row.transit
    && e.meta?.natal_planet === row.natal
    && e.meta?.aspect_type === row.aspect) || null;
}
