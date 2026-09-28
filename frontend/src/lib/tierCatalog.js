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
  FREE_TRANSITS_TEASER_MONTHS, TIER_NAMES, TIER_NAMES_GENITIVE, TIER_PDF_PER_MONTH,
} from '../constants';
import { offerFor } from './offerRule';
import { TIER_WORDS } from './interpretationUpsell';

export const CATALOG_TIERS = ['free', 'lite', 'pro', 'premium'];

/**
 * Срок оплаты — одна формулировка на веб и приложение. Бэкенд даёт 30 дней
 * с даты оплаты (payments/common.PERIOD_DAYS), продление прибавляет 30 дней
 * к концу срока. До 29.09.2026 на вебе было «на 1 месяц», в приложении —
 * «за 30 дней».
 */
export const ACCESS_TERM = 'Доступ на 30 дней, без автопродления';

/** Числа тарифов. null — без лимита. Сверка с TIER_FLAGS — в тесте. */
export const LIMITS = {
  //        сохранённые  разборы карты      разборы транзитов  чат           горизонт   лунный кал. Google
  //        карты        (free — на карту)  (free — на пробу)  (free — проба) транзитов  месяцев     Календарь
  free:    { charts: 2,    readings: 1,    transits: 2,    chat: 3,    horizon: FREE_TRANSITS_TEASER_MONTHS, lunar: 1, gcal: 0 },
  lite:    { charts: 5,    readings: 5,    transits: 15,   chat: 30,   horizon: 6,  lunar: 12,   gcal: 1 },
  pro:     { charts: 15,   readings: 15,   transits: null, chat: null, horizon: 12, lunar: 12,   gcal: null },
  premium: { charts: null, readings: null, transits: null, chat: null, horizon: 24, lunar: null, gcal: null },
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
// Лента кончается там же, где тарифный горизонт транзитов (feed/horizon.py),
// поэтому срок планера — то же число, а не «весь горизонт ленты».
const ahead = (t) => `на ${months(LIMITS[t].horizon)} вперёд`;

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
    // Прошлое в ленте — ровно месяц от сегодня у всех тарифов
    // (feed/horizon.py PAST_MONTHS), вперёд — тарифный горизонт транзитов.
    value: (t) => (t === 'free' ? 'текущая неделя и прошедший месяц' : ahead(t)),
  },
  {
    key: 'planner_period',
    title: 'Периоды Солнца–Марса',
    // Пояснение не должно обещать бесплатному все четыре планеты — это
    // описание пункта, а что открыто на тарифе, говорит значение.
    about: 'Солнце, Меркурий, Венера и Марс проходят по твоим домам — у каждого периода свои рекомендации.',
    where: 'both',
    value: (t) => (t === 'free' ? 'текущий период Солнца' : `все, ${ahead(t)}`),
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
      return n === null ? 'без лимита' : `до ${n}`;
    },
  },
  {
    key: 'transit_horizon',
    title: 'Транзиты вперёд',
    // И на сайте, и в ленте приложения: лента кончается там же, где
    // тарифный горизонт транзитов (backend/feed/horizon.py).
    where: 'both',
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
    // До 29.09.2026 здесь было «для одной карты» у всех платных: у Лиры
    // значение совпадало с Вегой, и пункт выпадал из её карточки — на
    // /pricing Лира будто не давала экспорта вовсе. Число — TIER_FLAGS
    // gcal_charts, сверяет тест.
    value: (t) => {
      const n = LIMITS[t].gcal;
      if (n === 0) return null;
      return n === null ? 'для всех карт' : 'для одной карты';
    },
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
  gcal_all: 'gcal',
};

export function catalogItem(feature) {
  return BY_KEY[FOCUS_ALIAS[feature] || feature] || null;
}

export function lineText(item, tier) {
  const v = item.value(tier);
  return v === true ? item.title : `${item.title} — ${v}`;
}

/**
 * Главные пункты тарифа — то, что окно предложения показывает под
 * подсвеченной строкой (решение владельца 29.09.2026: 3–4 пункта и ссылка
 * «Все возможности тарифа», полный список — только на /pricing). Порядок —
 * порядок показа. Пункт, ради которого открыли окно, из списка выпадает:
 * он уже стоит первым.
 */
export const OFFER_MAIN = {
  lite: ['chart_reading', 'transit', 'chat', 'planner_period'],
  pro: ['chat', 'transit', 'planner_longterm', 'chart_reading'],
  premium: ['crm', 'chart_reading', 'charts'],
};
const OFFER_MAIN_MAX = 4;   // вместе с подсвеченной строкой

// Куда ведёт «Все возможности тарифа» из приложения (там нет роутера сайта).
export const PRICING_URL = 'https://aristeatime.ru/pricing';

function fromLine(prev) {
  if (!prev) return null;
  return prev === 'free' ? 'Всё, что есть бесплатно, плюс:' : `Всё из ${TIER_NAMES_GENITIVE[prev]}, плюс:`;
}

/** «pdf-отчёт…» не пишем: латиница в начале остаётся заглавной. */
function lowerFirst(t) {
  return /^[А-ЯЁ]/.test(t) ? t[0].toLowerCase() + t.slice(1) : t;
}

/**
 * Карточка тарифа.
 *
 * @param {string} tier
 * @param {{surface?: 'web'|'app', focus?: string, full?: boolean}} [opts]
 *   focus — что человек пытался открыть (ключ offerRule.js или каталога):
 *     этот пункт встаёт первой строкой с `hl: true`, даже если тариф его не
 *     меняет, — предложение начинается с того, за чем человек пришёл;
 *   full — все пункты тарифа, а не только новые (карточка текущего тарифа);
 *   brief — окно предложения: подсвеченная строка + главные пункты
 *     (OFFER_MAIN), всего не больше четырёх.
 * @returns {{from: string|null, lines: {key, text, hl, about}[], site: string|null}}
 */
export function tierCard(tier, { surface = 'web', focus, full = false, brief = false } = {}) {
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
  const rest = brief
    ? (OFFER_MAIN[tier] || []).map((k) => BY_KEY[k]).filter((i) => i && i.value(tier) !== null)
    : own;
  for (const i of rest) {
    if (!shown(i) || i === focusItem) continue;
    if (brief && lines.length >= OFFER_MAIN_MAX) break;
    lines.push({ key: i.key, text: lineText(i, tier), hl: false, about: i.about || null });
  }

  // В приложении то, что есть только на сайте, — одной короткой строкой из
  // названий, без значений: «На сайте: лунный календарь, PDF-отчёт по карте».
  // До 29.09.2026 здесь была сплошная строка значений через «;».
  const site = surface === 'app' && !brief
    ? own.filter((i) => i.where === 'web').map((i) => lowerFirst(i.title))
    : [];
  return {
    from: fromLine(prev),
    lines,
    site: site.length ? `На сайте: ${site.join(', ')}` : null,
  };
}

/**
 * Текст замка: что закрыто и на каком тарифе открывается — пункт каталога,
 * его значение на том тарифе и сам тариф по offerRule. Решение владельца
 * 29.09.2026: замок в планере писал «периоды Марса, Венеры, Сатурна… на
 * тарифе Вега», а Сатурн — долгосрочные периоды, и они на Лире. Своих
 * перечислений планет в замках больше нет.
 *
 * «Долгосрочные периоды: Юпитер, Сатурн, Уран, Нептун, Плутон — на тарифе Лира.»
 */
export function lockText(feature, tier) {
  const item = catalogItem(feature);
  const o = offerFor(feature, tier || 'free', { sellable: ['lite', 'pro'] });
  if (!item || !o) return '';
  const v = item.value(o.primary);
  const what = v && v !== true ? `${item.title}: ${v}` : item.title;
  return `${what} — на тарифе ${TIER_NAMES[o.primary]}.`;
}

/** Первые n строк карточки — для старых окон сравнения, пока их не заменило
 * одно окно предложения (TierOfferModal). */
export function tierFeatures(tierId, n) {
  const lines = tierCard(tierId).lines.map((l) => l.text);
  return n ? lines.slice(0, n) : lines;
}

const MONTHS_GEN = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля',
  'августа', 'сентября', 'октября', 'ноября', 'декабря'];

/** «2026-10-01» → «1 октября». Даты присылает бэкенд, уже по МСК. */
export function resetDateWords(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || '');
  return m ? `${Number(m[3])} ${MONTHS_GEN[Number(m[2]) - 1]}` : null;
}

/**
 * Даты лимитов из ответа сервера: /profile/subscription (usage_resets_on,
 * usage_access_until) или кадр quota чата (resets_on, access_until).
 * resetsOn — счётчик обновится сам (оплачено продление или бесплатный месяц);
 * null — новые только после продления, тогда accessUntil — конец доступа.
 */
export function usageDatesFrom(src) {
  if (!src) return { resetsOn: null, accessUntil: null };
  return {
    resetsOn: src.usage_resets_on ?? src.resets_on ?? null,
    accessUntil: src.usage_access_until ?? src.access_until ?? null,
  };
}

/** « — обновятся 1 октября» / « — новые после продления, доступ до 29 октября». */
export function quotaTail(dates) {
  const d = typeof dates === 'string' ? { resetsOn: dates } : (dates || {});
  const resets = resetDateWords(d.resetsOn);
  if (resets) return ` — обновятся ${resets}`;
  const until = resetDateWords(d.accessUntil);
  return until ? ` — новые после продления, доступ до ${until}` : '';
}

/**
 * Что случилось — вторая строка окна предложения, когда кончился лимит.
 * period: 'trial' | 'month'; dates — usageDatesFrom(ответ сервера). Счётчики
 * платных — за оплаченный период (30 дней от оплаты), не за календарный
 * месяц, поэтому «этого месяца» здесь не пишется. Даты на клиенте не
 * вычисляются (решение владельца 28.09.2026): без них хвоста нет.
 */
export function quotaEndedText(feature, period, dates) {
  const item = catalogItem(feature);
  if (!item) return null;
  const tail = quotaTail(dates);
  if (item.key === 'chat') {
    return period === 'trial' ? 'Пробные сообщения закончились' : `Сообщения закончились${tail}`;
  }
  if (item.key === 'transit') {
    return period === 'trial' ? 'Пробные разборы транзитов закончились' : `Разборы транзитов закончились${tail}`;
  }
  return null;
}
