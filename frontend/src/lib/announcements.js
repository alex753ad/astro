/**
 * announcements.js — объявления для баннера (веб и приложение).
 *
 * Сегодня единственный источник — уведомление о смене цен (оферта п. 10.1
 * требует публикации, backend/payments/price_notice.py). Ручка публичная:
 * смена цен касается и тех, кто ещё не вошёл.
 *
 * Закрытый крестиком баннер запоминается по `ref` в localStorage — это
 * удобство одного устройства, а не состояние: письмо об изменении уходит всем
 * отдельно, баннер его только дублирует.
 */

import { API_BASE } from '../config';

const DISMISSED_KEY = 'aristea_dismissed_announcements';

export async function fetchAnnouncements(fetcher = fetch) {
  // Пререндер (headless-хром, scripts/prerender.mjs) баннер не запекает:
  // объявление временное, а снятый HTML живёт до следующей сборки.
  if (typeof navigator !== 'undefined' && navigator.webdriver) return [];
  try {
    const resp = await fetcher(`${API_BASE}/payments/announcements`);
    if (!resp.ok) return [];
    const body = await resp.json();
    return Array.isArray(body?.items) ? body.items : [];
  } catch {
    return [];   // без сети баннера просто нет — это не ошибка экрана
  }
}

function dismissed() {
  try { return new Set(JSON.parse(localStorage.getItem(DISMISSED_KEY) || '[]')); } catch { return new Set(); }
}

export function visibleAnnouncements(items) {
  const hidden = dismissed();
  return items.filter((a) => a?.ref && !hidden.has(a.ref));
}

export function dismissAnnouncement(ref) {
  const all = dismissed();
  all.add(ref);
  try { localStorage.setItem(DISMISSED_KEY, JSON.stringify([...all])); } catch { /* только до перезапуска */ }
}
