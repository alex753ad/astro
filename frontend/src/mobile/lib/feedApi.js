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
import { failWith, getWithRetry } from './authFetchTimeout';
import { localToday, shiftDays } from './feedTime';
import { offlineCache, rememberCharts, trimFeed } from './offlineCache';

// Таймаут запроса вынесен в authFetchTimeout.js 06.09.2026, когда у него
// появился второй потребитель (экран «Карта»). Там же — разбор, почему это
// Promise.race, а не AbortController.

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
 *
 * Отдаёт карту целиком, а не один идентификатор: шапке чата нужно ещё и имя
 * (SPEC_CHAT.md §3), а второй запрос ради поля, которое уже приехало в этом
 * же ответе, был бы лишним — тем более на холодном старте, где залп запросов
 * и так был причиной отдельного разбора (CLAUDE.md, «Холодный старт»).
 */
export async function resolvePrimaryChart() {
  const resp = await getWithRetry(`${API_BASE}/profile/charts`);
  if (!resp.ok) await failWith(resp, 'Не удалось получить список карт.');
  const data = await resp.json();
  const primary = pickPrimaryChart(data?.charts);
  await rememberCharts(data, primary?.id ?? null);
  return primary;
}

/** Тот же запрос, когда нужен только идентификатор. */
export async function resolvePrimaryChartId() {
  return (await resolvePrimaryChart())?.id ?? null;
}

/**
 * Та же выборка, но по уже загруженному списку — без своего запроса.
 *
 * ⚠️ Вынесена отдельной функцией, а не скопирована во второе место:
 * правило «основная, иначе первая» обязано быть ОДНИМ на приложение (тот
 * же довод, по которому chartApi.js берёт resolvePrimaryChartId отсюда, а
 * не пишет её у себя). Второй потребитель — «Ещё»: там список карт уже
 * загружен, и ссылка на веб-отчёт обязана вести на ту же карту, которую
 * показывают «Лента» и «Карта».
 */
export function pickPrimaryChart(charts) {
  if (!Array.isArray(charts) || charts.length === 0) return null;
  return charts.find((c) => c.is_primary) || charts[0];
}

/** То же правило, когда нужен только идентификатор. */
export function pickPrimaryChartId(charts) {
  return pickPrimaryChart(charts)?.id ?? null;
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
  const resp = await getWithRetry(url);

  if (resp.status === 404) {
    throw new Error('Карта не найдена. Построй её заново на вкладке «Карта».');
  }
  if (!resp.ok) await failWith(resp, 'Не удалось загрузить ленту.');
  return resp.json();
}

/**
 * Лента для показа без сети: карта (id и имя — шапке чата) и обрезанная
 * лента (`trimFeed`). Одна запись на обе, чтобы карта и лента не
 * разошлись.
 */
export function rememberFeed(chart, feed, today = localToday()) {
  return offlineCache.write('feed', { chart: { id: chart.id, name: chart.name }, feed: trimFeed(feed, today) });
}

export async function cachedFeed() {
  const hit = await offlineCache.read('feed');
  return hit?.data?.chart?.id && hit.data.feed ? { ...hit.data, savedAt: hit.savedAt } : null;
}
