/**
 * chartApi.js — два запроса экрана «Карта» и больше ничего (§2 спецификации).
 *
 *   1. GET /profile/charts — какую карту показывать. Выбор тот же, что в
 *      ленте, поэтому `resolvePrimaryChartId` берётся из feedApi.js, а не
 *      пишется здесь второй раз: правило «основная, иначе первая» обязано
 *      быть одним на приложение — иначе лента и карта покажут разное.
 *   2. GET /chart/{id} — вся карта разом: планеты, дома, аспекты, углы.
 *      Третьего запроса на этом экране нет (проверено разведкой,
 *      CHART_API_RECON.md §2).
 *
 * Разбора карты здесь нет намеренно — он не входит в этот заход (§1
 * спецификации), а не «забыт».
 */

import { API_BASE } from '../../config';
import { responseErrorText } from '../../api/client';
import { authFetchWithTimeout } from './authFetchTimeout';
import { buildChartPayload } from './chartCreateRules';

export { resolvePrimaryChartId } from './feedApi';

/**
 * Карта целиком.
 *
 * ⚠️ 404 перехватывается намеренно: сервер отвечает
 * «Chart not found: 3f2a…-uuid», и показывать пользователю внутренний
 * идентификатор нельзя. Тот же приём и по той же причине, что в
 * fetchFeed — 404 здесь означает и «нет карты», и «нет доступа»
 * (resolve_chart_access отвечает одинаково, это не утечка, а защита).
 */
export async function fetchChart(chartId) {
  const resp = await authFetchWithTimeout(`${API_BASE}/chart/${chartId}`);

  if (resp.status === 404) {
    // Статус приклеен намеренно: по нему ChartScreen отличает «нет карты,
    // которую я сам только что показывал» (её удалили в «Ещё») от общего
    // отказа и снимает своё переопределение вместо тупика до перезапуска.
    const err = new Error('Карта не найдена. Возможно, она удалена.');
    err.status = 404;
    throw err;
  }
  if (!resp.ok) {
    throw new Error(await responseErrorText(resp, 'Не удалось загрузить карту.'));
  }
  return resp.json();
}

/**
 * Построение карты — `POST /chart/calculate` (SPEC_CHART_CREATE.md).
 *
 * ⚠️ Свой предел ожидания, а не общие 15 секунд: долгая работа здесь норма,
 * а не признак зависания (§9 спецификации). Геокодинг сериализован
 * семафором на весь процесс сервера с паузой 1.1 с между запросами к
 * Nominatim, дальше карту целиком считает Swiss Ephemeris.
 *
 * ⚠️ Отказ бросается СТРУКТУРНО — с `status` и сырым `detail`, — а не
 * человеческим текстом, как в `fetchChart` рядом. Разница не в стиле: у
 * этой ручки 400 значит две разные вещи в зависимости от ФОРМЫ `detail`
 * (объект `ambiguous_time` — ветка с выбором времени, строка — неудачный
 * геокодинг), и склеив их в строку, отличить одно от другого было бы уже
 * нечем. Разбирает `describeCreateError` (`chartCreateRules.js`), он же
 * покрыт тестами.
 *
 * Тела запроса собирает `buildChartPayload` — координат в нём нет и быть не
 * может: ручка их из тела не принимает и геокодирует `birth_place` сама.
 */
export const CREATE_CHART_TIMEOUT_MS = 45000;

export async function createChart(form) {
  const resp = await authFetchWithTimeout(
    `${API_BASE}/chart/calculate`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(buildChartPayload(form)),
    },
    CREATE_CHART_TIMEOUT_MS,
  );

  if (resp.ok) return resp.json();

  const body = await resp.json().catch(() => null);
  const detail = body?.detail;
  const err = new Error(
    (typeof detail === 'string' && detail) || 'Не удалось построить карту. Попробуй ещё раз.',
  );
  err.status = resp.status;
  err.detail = body;
  throw err;
}

/**
 * Публичная ссылка на карту — `POST /api/v1/charts/{id}/share`
 * (`backend/share_router.py:174`).
 *
 * ⚠️ Путь `/charts/` (множественное), а не `/chart/` как у соседей в этом
 * файле. Это не опечатка: ручка живёт в отдельном роутере со своим
 * префиксом, и обе формы существуют в API одновременно.
 *
 * ⚠️ `card_url` берётся из ответа КАК ЕСТЬ и не собирается из `API_BASE`.
 * Веб собирает его сам (`ChartPage.jsx:455`), и это работает только потому,
 * что там API и сайт на одном домене. В приложении origin —
 * `https://localhost`, и та же сборка дала бы неоткрываемый адрес. Сервер
 * строит оба URL от своего `APP_URL` (`share_router.py:223-225`), он и
 * является источником истины.
 *
 * Повторный вызов по живому токену возвращает ТУ ЖЕ ссылку и НЕ продлевает
 * срок (`share_router.py:195-201`) — то есть кнопку можно нажимать сколько
 * угодно, вечной ссылка от этого не станет.
 */
export async function createShareLink(chartId) {
  const resp = await authFetchWithTimeout(
    `${API_BASE}/charts/${chartId}/share`,
    { method: 'POST' },
  );

  if (!resp.ok) {
    throw new Error(await responseErrorText(resp, 'Не удалось создать ссылку.'));
  }

  const data = await resp.json().catch(() => null);

  // ⚠️ Неполный ответ — отказ, а не «поделимся тем, что дали». Пустой
  // `share_url` уехал бы в буфер обмена как `undefined`, и человек отправил
  // бы это в чат, ничего не заметив: копирование не показывает, что
  // скопировано. Тот же довод, что у пустого id в handleCreated.
  if (!data?.share_url || !data?.card_url) {
    throw new Error('Сервер не вернул ссылку. Попробуй ещё раз.');
  }

  return { shareUrl: data.share_url, cardUrl: data.card_url };
}
