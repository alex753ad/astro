import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { APP_SELLABLE, TIER_ORDER, offerFor, opensFeature } from './offerRule';

const FEATURES = ['planner_period', 'planner_moon', 'planner_longterm', 'transit', 'transit_limit', 'chat', 'chat_limit', 'interpretation'];

describe('правило предложения тарифа — все сочетания', () => {
  it('таблица ожиданий', () => {
    const expected = {
      free: { planner_period: 'lite', planner_moon: 'lite', planner_longterm: 'pro', transit: 'lite', transit_limit: 'pro', chat: 'lite', chat_limit: 'pro', interpretation: 'lite' },
      lite: { planner_period: null, planner_moon: null, planner_longterm: 'pro', transit: null, transit_limit: 'pro', chat: null, chat_limit: 'pro', interpretation: 'pro' },
      pro: { planner_period: null, planner_moon: null, planner_longterm: null, transit: null, transit_limit: null, chat: null, chat_limit: null, interpretation: null },
      premium: { planner_period: null, planner_moon: null, planner_longterm: null, transit: null, transit_limit: null, chat: null, chat_limit: null, interpretation: null },
    };
    for (const tier of TIER_ORDER) {
      for (const f of FEATURES) {
        expect(offerFor(f, tier)?.primary ?? null, `${tier} × ${f}`).toBe(expected[tier][f]);
      }
    }
  });

  it('разбор транзита и чат на free после пробных: Вега, и Лира рядом', () => {
    expect(offerFor('transit', 'free')).toEqual({ primary: 'lite', alt: 'pro' });
    expect(offerFor('chat', 'free')).toEqual({ primary: 'lite', alt: 'pro' });
    expect(offerFor('chat_limit', 'lite')).toEqual({ primary: 'pro', alt: null });
    expect(offerFor('transit_limit', 'lite')).toEqual({ primary: 'pro', alt: null });
  });

  it('предлагается только тариф, который функцию открывает, и никогда — текущий или ниже', () => {
    for (const tier of TIER_ORDER) {
      for (const f of FEATURES) {
        const o = offerFor(f, tier);
        if (!o) continue;
        expect(TIER_ORDER.indexOf(o.primary)).toBeGreaterThan(TIER_ORDER.indexOf(tier));
        if (f !== 'interpretation') expect(opensFeature(f, o.primary), `${tier} × ${f}`).toBe(true);
      }
    }
  });

  it('в приложении Орион не предлагается', () => {
    for (const tier of TIER_ORDER) for (const f of FEATURES) {
      const o = offerFor(f, tier);
      if (o) expect(APP_SELLABLE).toContain(o.primary);
    }
  });

  it('на вебе, где Орион продаётся, Лире предлагают Орион за объёмом', () => {
    expect(offerFor('interpretation', 'pro', { sellable: ['lite', 'pro', 'premium'] })).toEqual({ primary: 'premium', alt: null });
  });

  // Копия сетки сервера — только в части «кто открывает»; сверка с TIER_FLAGS.
  it('чат и разбор транзитов совпадают с TIER_FLAGS', () => {
    const src = readFileSync(fileURLToPath(new URL('../../../backend/auth/rate_limits.py', import.meta.url)), 'utf-8');
    const block = (t, next) => src.slice(src.indexOf(`"${t}": {`), next ? src.indexOf(`"${next}": {`) : undefined);
    const blocks = { free: block('free', 'lite'), lite: block('lite', 'pro'), pro: block('pro', 'premium') };
    expect(blocks.lite).toMatch(/"transits_ai_per_month":\s*3/);
    expect(blocks.pro).toMatch(/"transits_ai_per_month":\s*None/);
    // Чат: пробные у free, 30 в месяц у Веги, без лимита у Лиры.
    expect(blocks.free).toMatch(/"chat_trial":\s*3/);
    expect(blocks.lite).toMatch(/"chat_per_month":\s*30/);
    expect(blocks.free).toMatch(/"transits_ai_trial":\s*2/);
  });
});
