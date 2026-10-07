import { describe, it, expect } from 'vitest';
import { CHART_HINTS, CHART_HINTS_SKY } from './onboardingCopy';

// Шаг 9.5: под sky_event меняется только подсказка про аспекты.
describe('CHART_HINTS_SKY', () => {
  it('отличается от CHART_HINTS только шагом aspects', () => {
    expect(CHART_HINTS_SKY.map((h) => h.key)).toEqual(CHART_HINTS.map((h) => h.key));
    CHART_HINTS_SKY.forEach((h, i) => {
      if (h.key !== 'aspects') expect(h).toBe(CHART_HINTS[i]);
    });
    const text = (list) => list.find((h) => h.key === 'aspects').text;
    expect(text(CHART_HINTS)).toContain('Зелёные — спокойные, красные — напряжённые.');
    expect(text(CHART_HINTS_SKY)).toContain('Зелёные — гармония, красные — напряжение.');
  });
});
