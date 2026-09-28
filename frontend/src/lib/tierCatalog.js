/**
 * tierCatalog.js — что даёт каждый тариф. Один источник для веба (страница
 * тарифов, «Подписка» в профиле, окна предложений) и приложения (лист оплаты,
 * карточка тарифа в «Ещё»). Решение владельца 28.09.2026.
 *
 * Одно понятие — один термин (docs/tariffs.md, «Витрина»): «Разбор карты» (не
 * «интерпретация»), «Разбор транзитов» (не «разбор аспектов»). Глубина тарифа —
 * значением пункта («около 2500 слов»), а не отдельным термином вроде
 * «глубокий разбор».
 *
 * Числа — копия `TIER_FLAGS` (backend/auth/rate_limits.py); сверяет
 * tierCatalog.test.js. Там же проверка, что в строках нет «интерпретац»,
 * «AI», «ИИ».
 *
 * Карточка тарифа накопительная сама собой: в ней только пункты, значение
 * которых отличается от предыдущего тарифа, — отсюда «Всё из Веги, плюс:» без
 * ручного набора. Второго списка пунктов (как было в TIERS и appTiers.js,
 * разошедшихся по числам и словам) не заводить.
 */

import {
  FREE_TRANSITS_TEASER_MONTHS, TIER_NAMES_GENITIVE, TIER_PDF_PER_MONTH,
} from '../constants';
import { TIER_WORDS } from './interpretationUpsell';

export const CATALOG_TIERS = ['free', 'lite', 'pro', 'premium'];

/** Числа тарифов. null — без лимита. Сверка с TIER_FLAGS — в тесте. */
export const LIMITS = {
  //        сохранённые  разборы карты      разборы транзитов  чат           горизонт   лунный кал.
  //        карты        (free — на карту)  (free — на пробу)  (free — проба) транзитов  месяцев
  free:    { charts: 2,    readings: 1,    transits: 2,    chat: 3,    horizon: FREE_TRANSITS_TEASER_MONTHS, lunar: 1 },
  lite:    { charts: 5,    readings: 5,    transits: 15,   chat: 30,   horizon: 6,  lunar: 12 },
  pro:     { charts: 15,   readings: 15,   transits: null, chat: null, horizon: 12, lunar: 12 },
  premium: { charts: null, readings: null, transits: null, chat: null, horizon: 24, lunar: null },
};

function plural(n, [one, few, many]) {
  const m10 = n % 10;
  const m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return one;
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return few;
  return many;
}

const perMonth = (n) => (n === null ? 'без лимита' : `${n} в месяц`);
const months = (n) => `${n} ${plural(n, ['месяц', 'месяца', 'месяцев'])}`;

/**
 * Пункты витрины в порядке показа. `value(tier)` — значение на тарифе; null —
 * тариф пункт не даёт; true — пункт без значения (строка — одно название).
 * `where`: 'both' | 'web' | 'app' — в приложении веб-пункты уходят строкой
 * «На сайте», чтобы не обещать там невидимое.
 */
export const ITEMS = [
  {
    key: 'chart_reading',
    title: 'Разбор карты',
    about: 'Подробный текст о твоей натальной карте: характер, отношения, работа, деньги.',
    where: 'both',
    value: (t) => {
      const words = `около ${TIER_WORDS[t]} слов`;
      if (t === 'free') return `1 на каждую карту, ${words}`;
      return `${perMonth(LIMITS[t].readings)}, ${words}`;
    },
  },
  {
    key: 'transit',
    title: 'Разбор транзитов',
    about: 'Транзит — время, когда планета на небе задевает точку твоей карты. '
      + 'Разбор объясняет, что он значит для тебя и как его прожить.',
    where: 'both',
    value: (t) => (t === 'free' ? `${LIMITS.free.transits} на пробу` : perMonth(LIMITS[t].transits)),
  },
  {
    key: 'chat',
    title: 'Чат с Аристеей',
    about: 'Вопросы о твоей карте и о том, что идёт сейчас. '
      + 'Аристея отвечает с учётом твоей натальной карты и текущих транзитов.',
    where: 'both',
    value: (t) => {
      const n = LIMITS[t].chat;
      if (t === 'free') return `${n} ${plural(n, ['сообщение', 'сообщения', 'сообщений'])} на пробу`;
      return n === null ? 'без лимита' : `${n} ${plural(n, ['сообщение', 'сообщения', 'сообщений'])} в месяц`;
    },
  },
  {
    key: 'planner_moon',
    title: 'Луна по домам',
    about: 'Через какую сферу жизни проходит Луна и что в эти дни получается легче.',
    where: 'both',
    value: (t) => (t === 'free' ? 'текущая неделя и все прошедшие периоды' : 'на весь горизонт ленты'),
  },
  {
    key: 'planner_period',
    title: 'Периоды Солнца–Марса',
    about: 'Периоды Солнца, Меркурия, Венеры и Марса по твоим домам — с рекомендациями.',
    where: 'both',
    value: (t) => (t === 'free' ? 'текущий период Солнца' : 'все, на весь горизонт ленты'),
  },
  {
    key: 'planner_longterm',
    title: 'Долгосрочные периоды',
    about: 'Медленные планеты: темы, которые длятся месяцы и годы.',
    where: 'both',
    value: (t) => (t === 'pro' || t === 'premium' ? 'Юпитер, Сатурн, Уран, Нептун, Плутон' : null),
  },
  {
    key: 'forecast',
    title: 'Прогноз на день и на фазы Луны',
    where: 'app',
    value: () => true,
  },
  {
    key: 'charts',
    title: 'Сохранённые карты',
    about: 'Твоя карта и карты близких. Удалишь одну — место освободится.',
    where: 'both',
    value: (t) => {
      const n = LIMITS[t].charts;
      if (n === null) return 'без лимита';
      return t === 'free' ? String(n) : `до ${n}`;
    },
  },
  {
    key: 'transit_horizon',
    title: 'Транзиты вперёд',
    where: 'web',
    value: (t) => `на ${months(LIMITS[t].horizon)}`,
  },
  {
    key: 'lunar',
    title: 'Лунный календарь',
    where: 'web',
    value: (t) => {
      const n = LIMITS[t].lunar;
      if (n === null) return 'без ограничений по датам';
      return n === 1 ? 'текущий месяц' : 'на год';
    },
  },
  {
    key: 'gcal',
    title: 'Экспорт событий в Google Календарь',
    where: 'web',
    value: (t) => (t === 'free' ? null : 'для одной карты'),
  },
  {
    key: 'pdf',
    title: 'PDF-отчёт по карте',
    where: 'web',
    value: (t) => perMonth(TIER_PDF_PER_MONTH[t]),
  },
  {
    key: 'crm',
    title: 'Кабинет астролога',
    about: 'Клиенты, их карты и заметки в одном месте; PDF-отчёты с твоим именем.',
    where: 'web',
    value: (t) => (t === 'premium' ? true : null),
  },
];

const BY_KEY = Object.fromEntries(ITEMS.map((i) => [i.key, i]));

/** Ключи функций из offerRule.js → пункт каталога. */
const FOCUS_ALIAS = {
  interpretation: 'chart_reading',
  transit_limit: 'transit',
  chat_limit: 'chat',
  planner_period: 'planner_period',
  planner_moon: 'planner_moon',
  planner_longterm: 'planner_longterm',
};

export function catalogItem(feature) {
  return BY_KEY[FOCUS_ALIAS[feature] || feature] || null;
}

export function lineText(item, tier) {
  const v = item.value(tier);
  return v === true ? item.title : `${item.title} — ${v}`;
}

/**
 * Карточка тарифа.
 *
 * @param {string} tier
 * @param {{surface?: 'web'|'app', focus?: string, full?: boolean}} [opts]
 *   focus — что человек пытался открыть (ключ offerRule.js или каталога):
 *     этот пункт встаёт первой строкой с `hl: true`, даже если тариф его не
 *     меняет, — предложение начинается с того, за чем человек пришёл;
 *   full — все пункты тарифа, а не только новые (карточка текущего тарифа).
 * @returns {{from: string|null, lines: {key, text, hl, about}[], site: string|null}}
 */
export function tierCard(tier, { surface = 'web', focus, full = false } = {}) {
  const idx = CATALOG_TIERS.indexOf(tier);
  const prev = idx > 0 && !full ? CATALOG_TIERS[idx - 1] : null;
  const shown = (i) => i.where === 'both' || i.where === surface;
  const own = ITEMS.filter((i) => {
    const v = i.value(tier);
    return v !== null && (!prev || v !== i.value(prev));
  });

  const focusItem = focus ? catalogItem(focus) : null;
  const lines = [];
  if (focusItem && shown(focusItem) && focusItem.value(tier) !== null) {
    lines.push({ key: focusItem.key, text: lineText(focusItem, tier), hl: true, about: focusItem.about || null });
  }
  for (const i of own) {
    if (!shown(i) || i === focusItem) continue;
    lines.push({ key: i.key, text: lineText(i, tier), hl: false, about: i.about || null });
  }

  const siteLines = surface === 'app' ? own.filter((i) => i.where === 'web').map((i) => lineText(i, tier)) : [];
  return {
    from: prev ? `Всё из ${TIER_NAMES_GENITIVE[prev]}, плюс:` : null,
    lines,
    site: siteLines.length ? `На сайте: ${siteLines.join('; ')}` : null,
  };
}

const MONTHS_GEN = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля',
  'августа', 'сентября', 'октября', 'ноября', 'декабря'];

/** «2026-10-01» → «1 октября». Дату присылает бэкенд (usage_resets_on). */
export function resetDateWords(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || '');
  return m ? `${Number(m[3])} ${MONTHS_GEN[Number(m[2]) - 1]}` : null;
}

/**
 * Что случилось — вторая строка окна предложения, когда кончился лимит.
 * period: 'trial' | 'month'; resetsOn — дата из ответа бэкенда. Без даты хвост
 * «обновятся …» не пишется: вычислять её на клиенте нельзя (решение владельца
 * 28.09.2026) — сброс определяет сервер.
 */
export function quotaEndedText(feature, period, resetsOn) {
  const item = catalogItem(feature);
  if (!item) return null;
  const when = resetDateWords(resetsOn);
  const tail = when ? ` — обновятся ${when}` : '';
  if (item.key === 'chat') {
    return period === 'trial' ? 'Пробные сообщения закончились' : `Сообщения этого месяца закончились${tail}`;
  }
  if (item.key === 'transit') {
    return period === 'trial' ? 'Пробные разборы транзитов закончились' : `Разборы транзитов этого месяца закончились${tail}`;
  }
  return null;
}
