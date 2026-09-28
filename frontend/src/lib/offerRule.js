/**
 * offerRule.js — какой тариф предлагать в каком месте. Одно правило на веб и
 * приложение (решение владельца 27.09.2026, docs/tariffs.md).
 *
 * 1. Больше объёма (разбор карты подробнее): соседний тариф — free → Вега,
 *    Вега → Лира (`interpretationUpsell.js`, там же тексты).
 * 2. Конкретная закрытая функция: самый дешёвый тариф ИЗ ПРОДАВАЕМЫХ, который
 *    её открывает. У разбора транзита на free рядом вторым — Лира (без
 *    лимита), как в сравнении на вебе.
 * 3. В приложении продаются только Вега и Лира (`PaySheet.jsx`, SELLABLE):
 *    Ориона там не предлагаем — отсюда и «старший из доступных».
 *
 * Серверная сетка — `TIER_FLAGS` (backend/auth/rate_limits.py). Здесь копия
 * ТОЛЬКО ответа «кто открывает функцию»; разойдутся — человеку предложат
 * тариф, который ему ничего не даст. Держит `offerRule.test.js`.
 */

export const TIER_ORDER = ['free', 'lite', 'pro', 'premium'];
export const APP_SELLABLE = ['lite', 'pro'];

/** Какие тарифы открывают функцию целиком. */
const OPENED_BY = {
  planner_period: ['lite', 'pro', 'premium'],     // периоды Солнца–Марса
  planner_moon: ['lite', 'pro', 'premium'],       // Луна по домам вперёд
  planner_longterm: ['pro', 'premium'],           // Юпитер–Плутон
  // Разбор транзитов и чат — на free только на пробу (2 разбора и 3 сообщения
  // за всё время, решение владельца 28.09.2026); «открывает» здесь значит
  // «даёт регулярно»: Вега — в месяц, Лира — без лимита.
  transit: ['lite', 'pro', 'premium'],
  transit_limit: ['pro', 'premium'],              // разбор без месячного лимита
  chat: ['lite', 'pro', 'premium'],               // сообщения в месяц (Вега — 30)
  chat_limit: ['pro', 'premium'],                 // без лимита
};

const rank = (t) => TIER_ORDER.indexOf(t);

/** Открывает ли тариф функцию. */
export function opensFeature(feature, tier) {
  if (feature === 'interpretation') return false;   // объём — всегда «ещё больше»
  return (OPENED_BY[feature] || []).includes(tier);
}

/**
 * @param {string} feature — planner_period | planner_moon | planner_longterm |
 *   transit | transit_limit | chat | interpretation
 * @param {string} tier — текущий тариф
 * @param {{sellable?: string[]}} [opts] — что можно купить здесь
 * @returns {{primary: string, alt: string|null}|null} null — предлагать нечего
 */
export function offerFor(feature, tier, { sellable = APP_SELLABLE } = {}) {
  const above = (t) => rank(t) > rank(tier) && sellable.includes(t);
  if (feature === 'interpretation') {
    const next = TIER_ORDER[rank(tier) + 1];
    return next && sellable.includes(next) ? { primary: next, alt: null } : null;
  }
  if (!OPENED_BY[feature] || opensFeature(feature, tier)) return null;
  const candidates = TIER_ORDER.filter((t) => above(t) && opensFeature(feature, t));
  if (candidates.length === 0) return null;
  const primary = candidates[0];
  // На free после пробных: Вега (в месяц) и рядом Лира (без лимита) — у
  // разбора транзитов и у чата одинаково.
  const unlimited = { transit: 'transit_limit', chat: 'chat_limit' }[feature];
  const alt = unlimited && tier === 'free'
    ? (TIER_ORDER.find((t) => above(t) && opensFeature(unlimited, t) && t !== primary) || null)
    : null;
  return { primary, alt };
}
