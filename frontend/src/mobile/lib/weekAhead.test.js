import { describe, expect, it, vi } from 'vitest';

vi.mock('../../api/client', () => ({ authFetch: vi.fn() }));

const { findFeedEvent } = await import('./weekAhead');

const ROW = { date: '2026-10-07', transit: 'Saturn', natal: 'Moon', aspect: 'opposition' };
const EV = {
  kind: 'transit', at: '2026-10-07T16:49:00+03:00',
  meta: { transit_planet: 'Saturn', natal_planet: 'Moon', aspect_type: 'opposition' },
};

describe('findFeedEvent', () => {
  it('находит транзит того же дня', () => {
    expect(findFeedEvent([EV], ROW)).toBe(EV);
  });
  it('другой день или фаза Луны — null', () => {
    expect(findFeedEvent([EV], { ...ROW, date: '2026-10-08' })).toBeNull();
    expect(findFeedEvent([EV], { date: '2026-10-10', transit: 'new_moon', natal: null })).toBeNull();
  });
});
