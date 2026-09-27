import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { APP_LIMITS, APP_TIER_FEATURES } from './appTiers';

const src = readFileSync(fileURLToPath(new URL('../../../../backend/auth/rate_limits.py', import.meta.url)), 'utf-8');
const block = (t, next) => src.slice(src.indexOf(`"${t}": {`), src.indexOf(`"${next}": {`));
const num = (b, key) => {
  const m = b.match(new RegExp(`"${key}":\\s*(\\d+|None)`));
  expect(m, key).not.toBeNull();
  return m[1] === 'None' ? null : Number(m[1]);
};

describe('описания тарифов в приложении — те же числа, что TIER_FLAGS', () => {
  const blocks = { free: block('free', 'lite'), lite: block('lite', 'pro'), pro: block('pro', 'premium') };

  it('карты, разборы карты, разборы транзитов', () => {
    for (const t of ['free', 'lite', 'pro']) {
      expect(APP_LIMITS[t].charts, `${t} карты`).toBe(num(blocks[t], 'profiles_limit'));
    }
    for (const t of ['lite', 'pro']) {
      expect(APP_LIMITS[t].interpretations, `${t} разборы`).toBe(num(blocks[t], 'interpretations_per_month'));
      expect(APP_LIMITS[t].transits, `${t} транзиты`).toBe(num(blocks[t], 'transits_ai_per_month'));
    }
  });

  it('в приложенческих описаниях нет того, чего в приложении не видно', () => {
    const all = Object.values(APP_TIER_FEATURES).flat().join(' ');
    expect(all).not.toMatch(/Google|PDF|календар/i);
  });
});
