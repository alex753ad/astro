/**
 * feedApi.js — два запроса ленты и больше ничего.
 *
 * `authFetch` из api/client.js переиспользуется целиком: в нём уже сидит
 * обновление протухшего access-токена с однократным повтором запроса
 * (токен живёт 15 минут, без этого лента падала бы каждые четверть часа) и
 * мобильный транспорт refresh-токена. Свой fetch здесь завёл бы вторую,
 * отстающую копию этой логики.
 *
 * Запросов ровно два и оба обязательны:
 *
 *   1. GET /profile/charts — какую карту показывать. Ограничение «одна
 *      ручка» из спецификации касается СОДЕРЖИМОГО ленты, а не выбора
 *      карты (уточнено владельцем 05.09.2026): в мобильном приложении
 *      chart_id взять больше неоткуда — ChartScreen ещё заглушка, а
 *      localStorage-ключ astro_last_chart_id пишет только веб, на свежей
 *      установке он пуст.
 *   2. GET /chart/{id}/feed — сама лента.
 */

import { API_BASE } from '../../config';
import { authFetch, responseErrorText } from '../../api/client';
import { localToday, shiftDays } from './feedTime';

// Окно фиксированное, решение владельца 05.09.2026: месяц назад и 334 дня
// вперёд. Верхнюю границу по тарифу клиент НЕ считает — бэкенд сам обрежет
// запрос своим горизонтом, а настоящий край лента читает из horizon.to
// ответа. Так тарифная сетка остаётся в одном месте, на сервере.
//
// 365 дней помещаются в серверный лимит окна (366 суток, иначе 422). У
// Ориона горизонт 24 месяца — он в это окно не влезает и будет обрезан;
// дозагрузка остатка вынесена в отдельную задачу.
const PAST_DAYS = 31;
const FUTURE_DAYS = 334;

export function feedWindow(today = localToday()) {
  return { from: shiftDays(today, -PAST_DAYS), to: shiftDays(today, FUTURE_DAYS) };
}

/**
 * Карта, чью ленту показываем: помеченная основной, иначе первая по списку.
 * `null` — у аккаунта нет ни одной карты (состояние «нет карты», §11).
 */
export async function resolvePrimaryChartId() {
  const resp = await authFetch(`${API_BASE}/profile/charts`);
  if (!resp.ok) {
    throw new Error(await responseErrorText(resp, 'Не удалось получить список карт.'));
  }
  const charts = (await resp.json())?.charts;
  if (!Array.isArray(charts) || charts.length === 0) return null;
  return (charts.find((c) => c.is_primary) || charts[0]).id;
}

/**
 * Лента за окно. Возвращает ответ ручки как есть — ни сортировки, ни
 * фильтрации здесь нет: порядок задаёт бэкенд (§5), а что показывать,
 * решает экран.
 *
 * ⚠️ 404 перехватывается намеренно (§11): сервер отвечает
 * «Chart not found: 3f2a…-uuid», и показывать пользователю внутренний
 * идентификатор нельзя. Это известный долг сессии 04.09.2026, и до его
 * разбора на бэкенде текст подменяется здесь.
 */
export async function fetchFeed(chartId, { from, to }) {
  const url = `${API_BASE}/chart/${chartId}/feed?from_date=${from}&to_date=${to}`;
  const resp = await authFetch(url);

  if (resp.status === 404) {
    throw new Error('Карта не найдена. Постройте её заново на вкладке «Карта».');
  }
  if (!resp.ok) {
    throw new Error(await responseErrorText(resp, 'Не удалось загрузить ленту.'));
  }
  return resp.json();
}
