/**
 * feedReturn.js — куда вернуть ленту, когда человек пришёл на неё с другой
 * вкладки (решение владельца 27.09.2026: на тот же день, где оставил; при
 * первом открытии — на сегодня, это lib/feedAnchor.js).
 *
 * ⚠️ Зачем вообще что-то запоминать. Скроллер один на все вкладки
 * (TabShell.jsx), а неактивная вкладка прячется `display: none`. Уход на
 * «Карту» делает содержимое скроллера короче, браузер прижимает `scrollTop`
 * почти к нулю — и при возврате лента стояла в начале окна, на месяц назад.
 * Восстановить нечем: к моменту, когда эффект узнаёт об уходе, позиция уже
 * сброшена. Поэтому она запоминается ЗАРАНЕЕ, на каждой прокрутке.
 *
 * ⚠️ Запоминается день и отступ от его верха, а не пиксели. Пока человек на
 * «Карте», лента может обновиться (возврат из фона, перезапрос без сети) —
 * высоты карточек изменятся, и тот же `scrollTop` показал бы другой день.
 */

import { pickAnchorDate } from './feedAnchor';

/**
 * День у верхней кромки скроллера и насколько он ушёл за неё.
 *
 * @param {{date: string, top: number}[]} tops — верх секций дней (viewport),
 *   по возрастанию даты.
 * @param {number} edge — верх скроллера (viewport).
 * @returns {{date: string, offset: number}|null} offset > 0 — день начался
 *   выше кромки; < 0 — выше дня видна шапка ленты (прокручено к самому верху).
 */
export function topVisibleDay(tops, edge) {
  if (!Array.isArray(tops) || tops.length === 0) return null;
  let hit = tops[0];
  for (const t of tops) {
    if (t.top <= edge + 1) hit = t; else break;
  }
  return { date: hit.date, offset: edge - hit.top };
}

/**
 * Куда вернуться.
 *
 * Сохранённый день есть в ленте — на него, с тем же отступом. Пропал (лента
 * обновилась, день без событий ушёл) — на ближайший следующий, с его верха;
 * следующих нет — на последний. Ничего не сохранено (первое открытие, смена
 * карты) — на день-якорь, как при открытии.
 *
 * @param {{date: string, offset: number}|null} saved
 * @param {{date: string}[]} days — по возрастанию даты.
 * @param {string} today — «YYYY-MM-DD».
 * @returns {{date: string, offset: number}|null}
 */
export function returnTarget(saved, days, today) {
  if (!Array.isArray(days) || days.length === 0) return null;
  if (saved && days.some((d) => d.date === saved.date)) return { date: saved.date, offset: saved.offset };
  if (saved) {
    const next = days.find((d) => d.date > saved.date) || days[days.length - 1];
    return { date: next.date, offset: 0 };
  }
  return { date: pickAnchorDate(days, today), offset: 0 };
}
