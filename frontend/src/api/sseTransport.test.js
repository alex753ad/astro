/**
 * sseTransport.test.js — поток разбора без [DONE] не бывает «готово».
 *
 * До 24.09.2026 `_connectSSE` на обрыв после первых данных звал onDone:
 * оборванный разбор выглядел полным в вебе и в приложении, а приложение
 * сохраняло его на диск. Признак полного текста — только [DONE].
 *
 * EventSource подделан: тест сам шлёт кадры и рвёт соединение.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('./authTransport', () => ({
  AUTH_CREDENTIALS: 'omit',
  IS_MOBILE: false,
  authRequestBody: async () => undefined,
  clientHeaders: () => ({}),
  forgetRefreshToken: async () => {},
  rememberRefreshToken: async () => {},
}));

const sources = [];
class FakeEventSource {
  constructor(url) { this.url = url; this.closed = false; sources.push(this); }
  close() { this.closed = true; }
  send(data) { this.onmessage?.({ data, lastEventId: '' }); }
  drop() { this.onerror?.(); }
}

globalThis.EventSource = FakeEventSource;
globalThis.localStorage = { getItem: () => null, setItem() {}, removeItem() {} };

const { streamInterpretation } = await import('./client');
const { classifyOutcome, shouldCacheInterpretation, OUTCOMES } = await import('../mobile/lib/interpretRules');
const { createOfflineCache, rememberCharts, rememberInterpretation } = await import('../mobile/lib/offlineCache');

const tick = () => new Promise((r) => setTimeout(r, 0));

function run(chartId = 'c1') {
  const out = { chunks: [], done: false, error: null };
  streamInterpretation(
    chartId,
    (c) => out.chunks.push(c),
    () => { out.done = true; },
    (e) => { out.error = e; },
  );
  return out;
}

function memoryCache() {
  const map = new Map();
  const impl = {
    get: async ({ key }) => ({ value: map.get(key) ?? null }),
    set: async ({ key, value }) => { map.set(key, value); },
    remove: async ({ key }) => { map.delete(key); },
    keys: async () => ({ keys: [...map.keys()] }),
  };
  return { map, cache: createOfflineCache({ storage: async () => ({ plugin: impl }), owner: () => 'u1' }) };
}

beforeEach(() => { sources.length = 0; });

describe('_connectSSE: конец потока', () => {
  it('обрыв после первых данных — ошибка «Connection lost», а не готово', async () => {
    const out = run();
    await tick();
    sources[0].send(JSON.stringify({ text: 'Первые строки разбора' }));
    sources[0].drop();
    expect(out.done).toBe(false);
    expect(out.error).toBe('Connection lost');
  });

  it('после данных не переподключается: поток начался бы сначала и текст задвоился бы', async () => {
    run();
    await tick();
    sources[0].send(JSON.stringify({ text: 'кусок' }));
    sources[0].drop();
    await new Promise((r) => setTimeout(r, 1700));
    expect(sources).toHaveLength(1);
  });

  it('[DONE] — готово', async () => {
    const out = run();
    await tick();
    sources[0].send(JSON.stringify({ text: 'Полный текст' }));
    sources[0].send('[DONE]');
    expect(out.done).toBe(true);
    expect(out.error).toBeNull();
  });
});

describe('оборванный разбор не попадает в кэш', () => {
  it('обрыв после данных → failure → в кэше пусто', async () => {
    const out = run('c1');
    await tick();
    sources[0].send(JSON.stringify({ text: 'Половина разбора' }));
    sources[0].drop();

    const failure = classifyOutcome({ error: out.error });
    expect(failure.outcome).toBe(OUTCOMES.BROKEN);

    const sections = [{ name: '_intro', title: '', text: 'Половина разбора' }];
    const { cache, map } = memoryCache();
    await rememberCharts({ charts: [{ id: 'c1', is_primary: true }] }, 'c1', cache);
    if (shouldCacheInterpretation({ finished: true, failure, streamed: true, sections })) {
      await rememberInterpretation('c1', sections, cache);
    }
    expect([...map.keys()].some((k) => k.endsWith(':interp'))).toBe(false);
  });

  it('полный разбор ([DONE]) — сохраняется', async () => {
    const sections = [{ name: '_intro', title: '', text: 'Весь разбор' }];
    const failure = classifyOutcome({ error: null }).outcome === OUTCOMES.DONE ? null : 'x';
    expect(shouldCacheInterpretation({ finished: true, failure, streamed: true, sections })).toBe(true);
  });

  it('показанный с диска повторно не пишется', () => {
    expect(shouldCacheInterpretation({ finished: true, failure: null, streamed: false, sections: [{ text: 'a' }] })).toBe(false);
  });
});
