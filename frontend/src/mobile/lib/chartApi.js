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
    throw new Error('Карта не найдена. Постройте её заново на сайте.');
  }
  if (!resp.ok) {
    throw new Error(await responseErrorText(resp, 'Не удалось загрузить карту.'));
  }
  return resp.json();
}
