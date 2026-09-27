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
  transit: ['lite', 'pro', 'premium'],            // разбор любого транзита (на free — 2 значимых)
  transit_limit: ['pro', 'premium'],              // разбор без месячного лимита
  chat: ['pro', 'premium'],
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
  // Разбор транзита на free: Вега открывает 3 в месяц, Лира — без лимита.
  const alt = feature === 'transit' && tier === 'free'
    ? (TIER_ORDER.find((t) => above(t) && opensFeature('transit_limit', t) && t !== primary) || null)
    : null;
  return { primary, alt };
}
