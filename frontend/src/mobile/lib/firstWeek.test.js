import { beforeEach, describe, expect, it, vi } from 'vitest';

const authFetch = vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve({}) }));
let flagOn = false;
vi.mock('../../api/client', () => ({ authFetch: (...a) => authFetch(...a) }));
vi.mock('../../lib/flags', () => ({ isFlagOn: () => flagOn }));

const { markSeen } = await import('./firstWeek');

describe('markSeen', () => {
  beforeEach(() => { authFetch.mockClear(); });

  it('флаг выключен — ни одного запроса', () => {
    flagOn = false;
    markSeen('chart');
    expect(authFetch).not.toHaveBeenCalled();
  });

  it('флаг включён — одна отметка за запуск', () => {
    flagOn = true;
    markSeen('forecast');
    markSeen('forecast');
    expect(authFetch).toHaveBeenCalledTimes(1);
    expect(JSON.parse(authFetch.mock.calls[0][1].body)).toEqual({ key: 'forecast' });
  });
});
