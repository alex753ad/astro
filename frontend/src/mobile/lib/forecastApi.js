/**
 * forecastApi.js — прогнозы для приложения: на сегодня и на фазу Луны.
 *
 * Ручки — backend/forecast/router.py. Текст генерируется при ПЕРВОМ открытии
 * и кэшируется на сервере, поэтому первый запрос дня может идти несколько
 * секунд: таймаут здесь длиннее, чем у ленты.
 *
 * ⚠️ Пояс телефона уходит в каждый запрос (решение владельца 23.09.2026):
 * «сегодня» — по часам человека, а не по месту рождения. Без пояса сервер
 * возьмёт пояс карты.
 */

import { API_BASE } from '../../config';
import { authFetchWithTimeout } from './authFetchTimeout';
import { lunationPhase } from './lunationPhase';

const FORECAST_TIMEOUT_MS = 45000;

export function deviceTimeZone() {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || '';
  } catch {
    return '';
  }
}

function withTz(url, tz = deviceTimeZone()) {
  return tz ? `${url}${url.includes('?') ? '&' : '?'}tz=${encodeURIComponent(tz)}` : url;
}

async function getJson(url) {
  const resp = await authFetchWithTimeout(url, {}, FORECAST_TIMEOUT_MS);
  if (!resp.ok) throw new Error(`forecast ${resp.status}`);
  return resp.json();
}

/** { date, paragraphs[], source, trimmed } */
export function fetchTodayForecast(chartId, tz) {
  return getJson(withTz(`${API_BASE}/chart/${chartId}/forecast/today`, tz));
}

/**
 * Прогноз на фазу по событию ленты `moon_phase`.
 * Дата — местная дата из `event.at`; сервер сам найдёт точный момент фазы.
 * { phase, sign, at, headline, sign_meaning, actions[], warning|null, closing, source, trimmed }
 */
export function fetchLunationForecast(chartId, event, tz) {
  const phase = lunationPhase(event);
  const date = (event?.at || '').slice(0, 10);
  return getJson(withTz(
    `${API_BASE}/chart/${chartId}/forecast/lunation?phase=${encodeURIComponent(phase)}&date=${date}`,
    tz,
  ));
}
