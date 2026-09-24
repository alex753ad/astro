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
import { failWith, getWithRetry } from './authFetchTimeout';
import { localToday } from './feedTime';
import { lunationPhase } from './lunationPhase';
import { dayForecastKey, lunationForecastKey, offlineCache, rememberForecast } from './offlineCache';

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
  const resp = await getWithRetry(url, FORECAST_TIMEOUT_MS);
  if (!resp.ok) await failWith(resp, 'Прогноз не загрузился.');
  return resp.json();
}

async function getAndRemember(url, name) {
  const data = await getJson(url);
  await rememberForecast(name, data, localToday());
  return data;
}

async function cached(name) {
  return (await offlineCache.read(name)) || null;
}

/**
 * Прогноз на местную дату «YYYY-MM-DD»: вчера, сегодня, завтра (с 19:00).
 * Какие даты открыты — feedAnchor.js (forecastDates), сервер держит ту же
 * границу и на остальное отвечает 404.
 * { date, paragraphs[], source, trimmed }
 */
export function fetchDayForecast(chartId, date, tz) {
  return getAndRemember(
    withTz(`${API_BASE}/chart/${chartId}/forecast/day?date=${date}`, tz),
    dayForecastKey(chartId, date),
  );
}

/**
 * Сохранённый прогноз ровно на эту дату: `{ data, savedAt }` или null.
 * ⚠️ Ключ — дата карточки, поэтому вчерашний текст под «сегодня» не
 * попадёт никогда: у сегодняшней карточки другой ключ.
 */
export function cachedDayForecast(chartId, date) {
  return cached(dayForecastKey(chartId, date));
}

/**
 * Прогноз на фазу по событию ленты `moon_phase`.
 * Дата — местная дата из `event.at`; сервер сам найдёт точный момент фазы.
 * { phase, sign, at, headline, sign_meaning, actions[], warning|null, closing, source, trimmed }
 */
export function fetchLunationForecast(chartId, event, tz) {
  const phase = lunationPhase(event);
  const date = (event?.at || '').slice(0, 10);
  return getAndRemember(
    withTz(`${API_BASE}/chart/${chartId}/forecast/lunation?phase=${encodeURIComponent(phase)}&date=${date}`, tz),
    lunationForecastKey(chartId, phase, date),
  );
}

export function cachedLunationForecast(chartId, event) {
  return cached(lunationForecastKey(chartId, lunationPhase(event), (event?.at || '').slice(0, 10)));
}
