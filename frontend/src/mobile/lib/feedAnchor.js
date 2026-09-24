/**
 * feedAnchor.js — на каком дне открывается лента (§10 SPEC_FEED_SCREEN.md).
 *
 * Правило вынесено из FeedScreen отдельным файлом 16.09.2026, после того как
 * приёмка на устройстве показала ленту, открытую на месяц назад. Сама причина
 * была не здесь (полоска дней поднимала общий скроллер — разбор в
 * FeedDayStrip.jsx), но выяснилось это не сразу: правило выбора дня жило
 * одной строкой внутри рендера, и проверить его отдельно от прокрутки было
 * нечем. Теперь можно.
 *
 * ⚠️ Якорь — НЕ календарное «сегодня». Дни списка строятся из событий, дня без
 * событий в списке нет вовсе: при пустом сегодня раскрывать и прокручивать
 * было бы не к чему. Поэтому берётся первый день НЕ РАНЬШЕ сегодняшнего, а
 * если и таких нет (окно целиком в прошлом) — последний из имеющихся.
 *
 * ⚠️ Отсюда следствие, которое легко потерять: раскрытый день и сегодняшний
 * могут не совпасть, и подписывать чужой день «Сегодня» нельзя. Пометку
 * ставит заголовок и только настоящему сегодня (FeedDayHeader.jsx).
 */

import { shiftDays } from './feedTime';

/**
 * @param {{date: string}[]} days — дни ленты, по возрастанию даты.
 * @param {string} today — локальная дата устройства, «YYYY-MM-DD».
 * @returns {string|null} дата дня-якоря либо null, если дней нет вовсе.
 */
/**
 * С этого часа (по часам телефона) открыт прогноз на завтра — у всех
 * (решение владельца 24.09.2026). Зеркало TOMORROW_OPEN_HOUR в
 * backend/forecast/router.py: разойдутся — карточка «завтра» откроется в 404.
 */
export const TOMORROW_OPEN_HOUR = 19;

/**
 * Даты, у которых в ленте есть карточка прогноза: вчера, сегодня и — с 19:00
 * — завтра. До 19:00 завтрашней карточки нет совсем, не заглушка (решение
 * владельца).
 */
export function forecastDates(today, hour) {
  const dates = [shiftDays(today, -1), today];
  if (hour >= TOMORROW_OPEN_HOUR) dates.push(shiftDays(today, 1));
  return dates;
}

/**
 * Добавить в список пустые дни для дат с прогнозом, если событий в них нет.
 *
 * С 23.09.2026 у сегодняшнего дня всегда есть содержание — карточка
 * прогноза; с 24.09.2026 то же у вчера и (с 19:00) у завтра. Без вставки
 * прогнозу в день без событий негде было бы стоять. Следствие для якоря:
 * сегодняшний день внутри окна теперь есть всегда, и лента открывается на нём.
 *
 * Не вставляется, если событий нет вовсе (для пустого окна у ленты своё
 * сообщение) и для дат вне окна `horizon`.
 *
 * @param {{date: string, events: object[]}[]} days — по возрастанию даты.
 * @param {string[]} dates — «YYYY-MM-DD».
 * @param {{from?: string, to?: string}} [horizon]
 */
export function withDates(days, dates, horizon = {}) {
  if (!Array.isArray(days) || days.length === 0) return days;
  let out = days;
  for (const date of dates) {
    if (horizon.from && date < horizon.from) continue;
    if (horizon.to && date > horizon.to) continue;
    if (out.some((d) => d.date === date)) continue;
    const i = out.findIndex((d) => d.date > date);
    out = out.slice();
    out.splice(i === -1 ? out.length : i, 0, { date, events: [] });
  }
  return out;
}

export function pickAnchorDate(days, today) {
  if (!Array.isArray(days) || days.length === 0) return null;
  const ahead = days.find((d) => d && d.date >= today);
  return (ahead || days[days.length - 1]).date;
}
