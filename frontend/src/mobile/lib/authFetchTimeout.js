/**
 * authFetchTimeout.js — `authFetch` с таймаутом. Один на все экраны.
 *
 * Без таймаута зависший запрос вешает экран в скелете НАВСЕГДА (найдено
 * 05.09.2026 на устройстве: приложение, возвращённое из фона после долгого
 * простоя, ждало ответа по уже мёртвому TCP-соединению бесконечно). Экран
 * обязан дойти до состояния «Не удалось загрузить» за конечное время
 * независимо от ПРИЧИНЫ зависания — таймаут закрывает это как класс, а не
 * только найденный случай.
 *
 * ⚠️ `AbortController` здесь не помогает и намеренно не используется:
 * `authFetch` при 401 сам вызывает `refreshAccessToken()` из client.js — у
 * ТОГО внутреннего fetch своего сигнала нет и снаружи его не передать, а
 * зависнуть может именно он (тот же протухший сокет). Наш abort отменил бы
 * только внешний запрос, а `authFetch` всё равно завис бы на ожидании
 * чужого промиса. Поэтому таймаут — это `Promise.race`, гарантирующий, что
 * ЭКРАН отпустит ожидание вовремя, даже если сам сетевой запрос где-то
 * внутри client.js остался висеть (мы больше не ждём его результата, но он
 * и не отменяется — осознанный компромисс: висящий экран хуже, чем висящий
 * фоновый fetch).
 *
 * Жил внутри feedApi.js до 06.09.2026, вынесен при появлении второго
 * потребителя (chartApi.js) — чтобы у экранов не завелось двух таймаутов
 * с разными числами и разными оговорками.
 */

import { authFetch, responseErrorText } from '../../api/client';
import { NetError, isFetchFailure } from './netError';

export const REQUEST_TIMEOUT_MS = 15000;

function timeout(ms, write) {
  let timer;
  const promise = new Promise((_, reject) => {
    timer = setTimeout(() => reject(new NetError('timeout', undefined, { write })), ms);
  });
  return { promise, clear: () => clearTimeout(timer) };
}

/**
 * @param {number} [timeoutMs] — свой предел для конкретного вызова.
 *
 * ⚠️ Умолчание в 15 секунд НЕ поднимаем ради одного долгого запроса: оно
 * описывает, сколько экран готов ждать зависшую сеть, и терпеливее его
 * делать значит работать против того, ради чего таймаут заведён. Свой
 * предел передаёт тот вызов, у которого долгая работа — норма, а не признак
 * зависания: построение карты ждёт геокодинг (семафор на весь процесс, 1.1 с
 * между запросами к Nominatim, до двух повторов при 429) и расчёт Swiss
 * Ephemeris — SPEC_CHART_CREATE.md §9.
 */
export function authFetchWithTimeout(url, options, timeoutMs = REQUEST_TIMEOUT_MS) {
  const write = Boolean(options?.method && options.method.toUpperCase() !== 'GET');
  const t = timeout(timeoutMs, write);
  // Отказ fetch без связи — TypeError «Failed to fetch»; переводим в NetError,
  // чтобы экран сказал «нет сети», а не показал текст браузера.
  const req = authFetch(url, options).catch((err) => {
    throw isFetchFailure(err) ? new NetError('offline', undefined, { write }) : err;
  });
  return Promise.race([req, t.promise]).finally(t.clear);
}

/**
 * Повторы — только для чтения и только там, где повтор может помочь
 * (решение владельца 24.09.2026):
 *
 *   · таймаут — один повтор: зависла сеть, второй раз обычно проходит;
 *   · 5xx — до двух повторов: сервер перезапускается, деплой;
 *   · нет сети — не повторяем: отказ мгновенный, повтор через секунду
 *     даст то же самое. Вернётся сеть — экран перезапросит сам;
 *   · 429 и прочие 4xx — не повторяем: это ответ по делу, а 429 от
 *     лимитера повтор только продлит.
 *
 * ⚠️ POST/PATCH/DELETE сюда не ходят никогда: повтор записи или оплаты
 * может сделать её дважды. Поэтому метод не параметр — функция только GET.
 */
export const RETRY_PAUSES_MS = [1000, 3000];

const sleep = (ms) => new Promise((r) => { setTimeout(r, ms); });

export function retryDecision(attempt, { error, status }) {
  if (attempt >= RETRY_PAUSES_MS.length) return null;
  if (error) return error.kind === 'timeout' && attempt < 1 ? RETRY_PAUSES_MS[attempt] : null;
  return status >= 500 ? RETRY_PAUSES_MS[attempt] : null;
}

export async function getWithRetry(url, timeoutMs = REQUEST_TIMEOUT_MS, fetcher = authFetchWithTimeout, wait = sleep) {
  for (let attempt = 0; ; attempt += 1) {
    let resp;
    try {
      resp = await fetcher(url, {}, timeoutMs);
    } catch (error) {
      const pause = retryDecision(attempt, { error });
      if (pause == null) throw error;
      await wait(pause);
      continue;
    }
    const pause = retryDecision(attempt, { status: resp.status });
    if (pause == null) return resp;
    await wait(pause);
  }
}

/** 5xx — NetError('server'); прочие отказы — текстом сервера. */
export async function failWith(resp, fallback) {
  if (resp.status >= 500) throw new NetError('server', resp.status);
  const err = new Error(await responseErrorText(resp, fallback));
  err.status = resp.status;
  throw err;
}
