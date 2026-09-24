/**
 * forecastPrefetch.test.js — какую фазу подгружать заранее.
 */
import { describe, expect, it } from 'vitest';
import { nextLunationEvent } from './forecastPrefetch';

const now = Date.parse('2026-09-24T12:00:00+03:00');

describe('nextLunationEvent', () => {
  it('первая фаза впереди, прошедшая и не-фазы пропускаются', () => {
    const events = [
      { kind: 'moon_phase', at: '2026-09-20T10:00:00+03:00', meta: { type: 'new_moon' } },
      { kind: 'transit', at: '2026-09-25T10:00:00+03:00' },
      { kind: 'moon_phase', at: '2026-09-26T10:00:00+03:00', meta: { type: 'first_quarter' } },
      { kind: 'eclipse', at: '2026-10-05T10:00:00+03:00', meta: { type: 'lunar' } },
      { kind: 'moon_phase', at: '2026-10-20T10:00:00+03:00', meta: { type: 'new_moon' } },
    ];
    expect(nextLunationEvent(events, now).at).toBe('2026-10-05T10:00:00+03:00');
  });

  it('нет фаз — null', () => {
    expect(nextLunationEvent([], now)).toBeNull();
    expect(nextLunationEvent(undefined, now)).toBeNull();
  });
});
