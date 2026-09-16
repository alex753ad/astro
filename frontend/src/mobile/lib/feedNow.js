/**
 * feedNow.js — отбор данных для полосы «сейчас» (§4, §6 SPEC_FEED_VISUAL.md).
 *
 * Вынесено из FeedNowStrip.jsx 15.09.2026, когда у полосы появился ВТОРОЙ
 * потребитель — компактная полоска поверх потока (FeedNowCompact.jsx). Обе
 * показывают одно и то же состояние: период Солнца, состояние Луны, планеты
 * по домам. Вторая копия этих выборок разъехалась бы с первой молча — именно
 * так в этом проекте уже расходились правила, живущие в двух местах.
 *
 * Здесь только ОТБОР и склонение чисел. Ни одной строки разметки: развёрнутая
 * полоса и компактная рисуют одни и те же данные по-разному, и общий вид им
 * не нужен — нужен общий факт.
 */

import { daysBetween } from './feedTime';
import { PLANNER_PLANET_ORDER } from './feedGlyphs';

/** «1 день» / «3 дня» / «5 дней» — остаток периода и срок до фазы (§6). */
export function pluralDays(n) {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return 'день';
  if ([2, 3, 4].includes(mod10) && ![12, 13, 14].includes(mod100)) return 'дня';
  return 'дней';
}

// Родительный падеж для «до …» (§6: «до полнолуния», «до новолуния»).
// Лента строит только эти два — квадратов (первая/последняя четверть) в
// /feed нет вовсе (см. builder.py: phase_events собирает только new_moon
// и full_moon).
const PHASE_GENITIVE = {
  new_moon: 'новолуния',
  full_moon: 'полнолуния',
};

/**
 * Строка 1 (§6) — текущий период Солнца: тот же planner_period, что уже
 * идёт в потоке ленты (не вторая выборка с другим правилом) — здесь просто
 * найден среди events тот единственный экземпляр, что покрывает сегодня.
 */
export function findSunPeriod(events, today) {
  return events.find((e) => (
    e.kind === 'planner_period'
    && e.meta?.planet === 'sun'
    && e.at.slice(0, 10) <= today
    && today <= (e.ends_at || '').slice(0, 10)
  )) || null;
}

/**
 * Строка 2 (§6) — состояние Луны: ближайшая фаза ВПЕРЁД от сегодня плюс
 * текущий знак Луны. Своей ручки под «текущий знак» у мобильного приложения
 * нет (§6 спецификации admits второй вариант — знак берётся из ближайшего
 * лунного транзита, а не из /calendar/lunar: третий запрос ради одной
 * строки нарушил бы правило feedApi.js «запросов ровно два»). Ближайший —
 * по минимальной разнице календарных дат с сегодня, не обязательно вперёд:
 * трактует «ближайший» буквально, как написано в спецификации.
 */
export function findMoonState(events, today) {
  const nextPhase = events
    .filter((e) => e.kind === 'moon_phase' && e.at.slice(0, 10) >= today)
    .sort((a, b) => (a.at < b.at ? -1 : 1))[0] || null;

  const moonTransits = events.filter((e) => e.kind === 'transit' && e.meta?.transit_planet === 'Moon');
  let nearestMoon = null;
  let nearestDiff = Infinity;
  for (const e of moonTransits) {
    const diff = Math.abs(daysBetween(today, e.at.slice(0, 10)));
    if (diff < nearestDiff) { nearestDiff = diff; nearestMoon = e; }
  }

  if (!nextPhase || !nearestMoon) return null; // §6: не хватает данных — строку не рисуем.

  return {
    currentSign: nearestMoon.meta.transit_sign,
    phaseGenitive: PHASE_GENITIVE[nextPhase.meta?.type] || 'фазы',
    phaseSign: nextPhase.meta?.sign,
    daysUntil: Math.max(0, daysBetween(today, nextPhase.at.slice(0, 10))),
  };
}

/**
 * Долгосрочные периоды для чипов (§4): по одному на медленную планету,
 * от самого короткого к самому длинному — НЕ по дате начала: периоды идут
 * одновременно, и хронология между ними бессмысленна.
 *
 * Копия перед сортировкой обязательна: массив приходит из состояния экрана,
 * и sort на месте перетасовал бы его там же.
 */
export function longtermChips(events) {
  return [...(events || []).filter((e) => e.kind === 'planner_longterm')]
    .sort((a, b) => (a.duration_days || 0) - (b.duration_days || 0));
}

/**
 * Полоса планет — все ТРИ горизонта планера одним рядом (решение владельца
 * 16.09.2026). По одной записи на планету, в порядке PLANNER_PLANET_ORDER.
 *
 * ⚠️ У всех значков ОДНА семантика — номер ДОМА. До 16.09.2026 в липкой
 * полосе «☉ 12» означало дни периода, а «♃ 11» — дом: два разных смысла в
 * одном ряду, различимых только по тому, знает ли человек, что у Юпитера не
 * бывает двенадцати дней. Дни периода остались словами в развёрнутой полосе и
 * в панели события.
 *
 * ⚠️ Берётся ТЕКУЩАЯ запись — та, что покрывает СЕЙЧАС. У Луны это важнее
 * всего: проходов по домам на окне полсотни, и без проверки в полосу попал бы
 * первый по списку, то есть месячной давности. Для медленных планет фильтр не
 * нужен — их в ленте по одной на планету, и выбирает её бэкенд тем же
 * правилом «период содержит сегодня».
 *
 * ⚠️ Сравнивается МОМЕНТ, а не календарная дата, и это не придирка к
 * точности. Луна меняет дом раз в ~2.3 суток, то есть почти всегда посреди
 * дня: 16.09 до 03:00 она в 12 доме, с 07:00 — в 3-м. По датам оба прохода
 * «покрывают сегодня», и в полосу попадал первый из них — вчерашний дом с
 * сегодняшней датой. Поймано собственным тестом при написании этого файла.
 *
 * ⚠️ Сравнение через `Date.parse`, а не строками: у событий ISO со смещением
 * карты, у устройства — своё, и лексикографически такие строки сравнивать
 * нельзя. Это не «арифметика над временем на клиенте» (её лента избегает
 * отдельным правилом) — новых времён здесь не считается, только сравнение
 * двух готовых.
 *
 * Планета без записи в полосу не попадает вовсе: пустой значок сообщал бы,
 * что горизонт есть, а данных нет, — а на деле нет и горизонта (например, у
 * карты без времени рождения планера нет целиком).
 */
export function plannerTimeline(events, nowMs = Date.now()) {
  const all = events || [];
  const covers = (e) => {
    const from = Date.parse(e.at);
    const to = Date.parse(e.ends_at || '');
    return Number.isFinite(from) && Number.isFinite(to) && from <= nowMs && nowMs <= to;
  };

  const byPlanet = new Map();
  for (const e of all) {
    const planet = e.meta?.planet;
    if (!planet || byPlanet.has(planet)) continue;
    if (e.kind === 'planner_longterm') {
      byPlanet.set(planet, e);
    } else if ((e.kind === 'planner_period' || e.kind === 'planner_moon_house') && covers(e)) {
      byPlanet.set(planet, e);
    }
  }

  return PLANNER_PLANET_ORDER
    .filter((planet) => byPlanet.has(planet))
    .map((planet) => byPlanet.get(planet));
}
