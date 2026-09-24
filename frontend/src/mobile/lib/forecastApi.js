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
import { authFetchWithTimeout, failWith, getWithRetry } from './authFetchTimeout';
import { localToday } from './feedTime';
import { withTz } from '../../lib/deviceTimezone';
import { lunationPhase } from './lunationPhase';
import { dayForecastKey, lunationForecastKey, offlineCache, rememberForecast } from './offlineCache';

const FORECAST_TIMEOUT_MS = 45000;

// Общий файл веба и приложения — второй копии заводить не нужно.
export { deviceTimeZone } from '../../lib/deviceTimezone';

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
 * Прогноз на местную дату «YYYY-MM-DD»: сегодня и завтра (с 19:00).
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
 * ⚠️ Ключ — дата карточки, поэтому завтрашний текст под «сегодня» не
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

/**
 * 👍/👎 под прогнозом: rating 1 | -1. Повторный вызов МЕНЯЕТ оценку, снять
 * её нельзя (решение владельца 24.09.2026). Без повторов — это запись.
 * `data` — ответ прогноза: версию промпта и источник сервер просит обратно,
 * потому что текст из офлайн-кэша мог быть написан прошлой версией.
 */
export async function sendForecastFeedback(chartId, { kind, ref, rating, data }) {
  const resp = await authFetchWithTimeout(`${API_BASE}/chart/${chartId}/forecast/feedback`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      kind, ref, rating, prompt_version: data.prompt_version, source: data.source,
    }),
  });
  if (!resp.ok) await failWith(resp, 'Оценка не сохранилась.');
}
