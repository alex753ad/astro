import { beforeEach, describe, expect, it } from 'vitest';
import { MIN_INTERVAL_MS, _resetForTests, refreshFlags, shouldRefresh } from './flags';

const ok = (flags) => async () => ({ ok: true, json: async () => ({ flags }) });

describe('shouldRefresh', () => {
  it('не чаще раза в MIN_INTERVAL_MS', () => {
    expect(shouldRefresh(1000 + MIN_INTERVAL_MS - 1, 1000, 't', 't')).toBe(false);
    expect(shouldRefresh(1000 + MIN_INTERVAL_MS, 1000, 't', 't')).toBe(true);
  });

  it('сменился аккаунт — сразу, флаги у людей разные', () => {
    expect(shouldRefresh(1001, 1000, 'new', 'old')).toBe(true);
    expect(shouldRefresh(1001, 1000, null, 'old')).toBe(true);
  });
});

describe('refreshFlags', () => {
  beforeEach(() => { _resetForTests(); });

  it('второй запрос в пределах интервала не уходит', async () => {
    let calls = 0;
    const fetcher = async (...a) => { calls += 1; return ok(['x'])(...a); };
    await refreshFlags(fetcher);
    await refreshFlags(fetcher);
    expect(calls).toBe(1);
  });

  it('сеть упала — не бросает', async () => {
    await expect(refreshFlags(async () => { throw new Error('offline'); })).resolves.toBeUndefined();
  });
});
