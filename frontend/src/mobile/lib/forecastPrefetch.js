/**
 * forecastPrefetch.js — подгрузить заранее то, что понадобится без сети
 * (решение владельца 24.09.2026): утро без сети должно быть с текстом.
 *
 * Ближайшая фаза — здесь: её прогноз открывается только из панели события,
 * сам он не загрузится.
 *
 * ⚠️ Завтрашнего прогноза здесь нет, и это не пропуск. С 19:00 карточка
 * «завтра» стоит в ленте (feedAnchor.js, forecastDates) и грузит себя сама —
 * лента рисует все дни сразу, — а ответ кладётся в кэш в forecastApi.js. До
 * 19:00 сервер на завтра отвечает 404 (TOMORROW_OPEN_HOUR), и раннюю выдачу
 * ради подгрузки владелец отклонил (вариант «а», 24.09.2026).
 */

import { cachedLunationForecast, fetchLunationForecast } from './forecastApi';
import { hasLunationForecast } from './lunationPhase';

/** Первая фаза, момент которой ещё впереди. */
export function nextLunationEvent(events, nowMs = Date.now()) {
  return (events || []).find((e) => hasLunationForecast(e) && Date.parse(e.at) >= nowMs) || null;
}

export async function prefetchLunation(chartId, events, nowMs = Date.now()) {
  const event = nextLunationEvent(events, nowMs);
  if (!chartId || !event) return;
  try {
    if (await cachedLunationForecast(chartId, event)) return;
    await fetchLunationForecast(chartId, event);
  } catch { /* подгрузка — фон; откроет панель — загрузит сама */ }
}
