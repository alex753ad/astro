/**
 * authFetchTimeout.test.js — повторы запросов (решение владельца 24.09.2026):
 * только GET, только таймаут и 5xx; 429 и прочие 4xx — никогда.
 */
import { describe, expect, it, vi } from 'vitest';

vi.mock('../../api/client', () => ({
  authFetch: vi.fn(),
  responseErrorText: async (_resp, fallback) => fallback,
}));

const { authFetch } = await import('../../api/client');
const { authFetchWithTimeout, getWithRetry, failWith } = await import('./authFetchTimeout');
const { NetError } = await import('./netError');

const resp = (status) => ({ ok: status < 400, status });

function scripted(outcomes) {
  const calls = [];
  const fetcher = async (url) => {
    calls.push(url);
    const next = outcomes[Math.min(calls.length - 1, outcomes.length - 1)];
    if (next instanceof Error) throw next;
    return resp(next);
  };
  return { fetcher, calls };
}

const noWait = async () => {};

describe('getWithRetry', () => {
  it('5xx — до двух повторов', async () => {
    const { fetcher, calls } = scripted([502, 503, 200]);
    expect((await getWithRetry('u', 1, fetcher, noWait)).status).toBe(200);
    expect(calls).toHaveLength(3);
  });

  it('5xx три раза подряд — отдаёт последний ответ после двух повторов', async () => {
    const { fetcher, calls } = scripted([500]);
    expect((await getWithRetry('u', 1, fetcher, noWait)).status).toBe(500);
    expect(calls).toHaveLength(3);
  });

  it.each([429, 404, 403, 401, 400])('%i не повторяется', async (status) => {
    const { fetcher, calls } = scripted([status, 200]);
    expect((await getWithRetry('u', 1, fetcher, noWait)).status).toBe(status);
    expect(calls).toHaveLength(1);
  });

  it('таймаут — один повтор', async () => {
    const { fetcher, calls } = scripted([new NetError('timeout'), new NetError('timeout'), 200]);
    await expect(getWithRetry('u', 1, fetcher, noWait)).rejects.toMatchObject({ kind: 'timeout' });
    expect(calls).toHaveLength(2);
  });

  it('нет сети — без повтора: отказ мгновенный, повтор даст то же', async () => {
    const { fetcher, calls } = scripted([new NetError('offline'), 200]);
    await expect(getWithRetry('u', 1, fetcher, noWait)).rejects.toMatchObject({ kind: 'offline' });
    expect(calls).toHaveLength(1);
  });

  it('пауза перед повтором — 1 с, потом 3 с', async () => {
    const { fetcher } = scripted([500, 500, 200]);
    const waits = [];
    await getWithRetry('u', 1, fetcher, async (ms) => { waits.push(ms); });
    expect(waits).toEqual([1000, 3000]);
  });
});

describe('authFetchWithTimeout', () => {
  it('«Failed to fetch» превращается в NetError offline', async () => {
    authFetch.mockRejectedValueOnce(new TypeError('Failed to fetch'));
    await expect(authFetchWithTimeout('u', {}, 1000)).rejects.toMatchObject({ kind: 'offline' });
  });

  it('прочие отказы проходят как есть', async () => {
    const bug = new Error('другое');
    authFetch.mockRejectedValueOnce(bug);
    await expect(authFetchWithTimeout('u', {}, 1000)).rejects.toBe(bug);
  });

  it('зависший запрос — NetError timeout', async () => {
    authFetch.mockReturnValueOnce(new Promise(() => {}));
    await expect(authFetchWithTimeout('u', {}, 10)).rejects.toMatchObject({ kind: 'timeout' });
  });

  it('POST не повторяется: authFetchWithTimeout зовёт fetch ровно раз', async () => {
    authFetch.mockClear();
    authFetch.mockResolvedValueOnce(resp(503));
    expect((await authFetchWithTimeout('u', { method: 'POST' }, 1000)).status).toBe(503);
    expect(authFetch).toHaveBeenCalledTimes(1);
  });
});

describe('failWith', () => {
  it('5xx — NetError server', async () => {
    await expect(failWith(resp(502), 'x')).rejects.toMatchObject({ kind: 'server', status: 502 });
  });

  it('4xx — текст сервера со статусом', async () => {
    await expect(failWith(resp(422), 'Не удалось.')).rejects.toMatchObject({ message: 'Не удалось.', status: 422 });
  });
});
