/**
 * offlineCache.test.js — хранилище для показа без сети.
 *
 * Плагин подделан тем же приёмом, что в api/authTransport.test.js: Proxy,
 * который на ЛЮБОЕ имя, включая `then`, отдаёт функцию. Если код хоть раз
 * вернёт или await-нет объект плагина, вызов повиснет — и тест упадёт по
 * таймауту гонки, а не пройдёт.
 */
import { describe, expect, it } from 'vitest';
import {
  CACHE_VERSION,
  cachedInterpretation,
  createOfflineCache,
  rememberCharts,
  rememberInterpretation,
  staleForecastNames,
  trimFeed,
} from './offlineCache';

function fakeStore() {
  const map = new Map();
  const impl = {
    get: async ({ key }) => ({ value: map.has(key) ? map.get(key) : null }),
    set: async ({ key, value }) => { map.set(key, value); },
    remove: async ({ key }) => { map.delete(key); },
    keys: async () => ({ keys: [...map.keys()] }),
  };
  const plugin = new Proxy({}, {
    get: (_, name) => impl[name] || (() => new Promise(() => {})),
  });
  return { map, storage: async () => ({ plugin }) };
}

function makeCache(owner = 'u1', store = fakeStore()) {
  let who = owner;
  const cache = createOfflineCache({ storage: store.storage, owner: () => who, now: () => 1000 });
  return { cache, store, setOwner: (o) => { who = o; } };
}

const race = (p) => Promise.race([p, new Promise((_, r) => setTimeout(() => r(new Error('ПОВИСЛО')), 500))]);

describe('запись и чтение', () => {
  it('отдаёт записанное вместе с моментом записи', async () => {
    const { cache } = makeCache();
    await race(cache.write('feed', { a: 1 }));
    expect(await race(cache.read('feed'))).toEqual({ data: { a: 1 }, savedAt: 1000 });
  });

  it('версия формата — в ключе', async () => {
    const { cache, store } = makeCache();
    await cache.write('feed', 1);
    expect([...store.map.keys()]).toEqual([`aristea_offline:v${CACHE_VERSION}:feed`]);
  });

  it('чужое не показывается и стирается', async () => {
    const { cache, store, setOwner } = makeCache('u1');
    await cache.write('me', { email: 'a' });
    setOwner('u2');
    expect(await cache.read('me')).toBeNull();
    expect(store.map.size).toBe(0);
  });

  it('без владельца (нет токена) ничего не пишется и не читается', async () => {
    const { cache, store, setOwner } = makeCache('u1');
    await cache.write('me', 1);
    setOwner(null);
    await cache.write('sub', 2);
    expect(await cache.read('me')).toBeNull();
    expect([...store.map.keys()].some((k) => k.endsWith(':sub'))).toBe(false);
  });

  it('битая запись выбрасывается молча', async () => {
    const { cache, store } = makeCache();
    store.map.set(`aristea_offline:v${CACHE_VERSION}:feed`, '{не json');
    expect(await cache.read('feed')).toBeNull();
    expect(store.map.size).toBe(0);
  });

  it('записи старой версии стираются при первом чтении', async () => {
    const store = fakeStore();
    store.map.set('aristea_offline:v0:feed', '{}');
    store.map.set('aristea_access_something', 'x');
    const { cache } = makeCache('u1', store);
    await cache.read('feed');
    expect([...store.map.keys()]).toEqual(['aristea_access_something']);
  });

  it('clearAll снимает все версии и только свои ключи', async () => {
    const store = fakeStore();
    store.map.set('aristea_offline:v0:x', '1');
    store.map.set('astro_refresh_token', 'r');
    const { cache } = makeCache('u1', store);
    await cache.write('feed', 1);
    await race(cache.clearAll());
    expect([...store.map.keys()]).toEqual(['astro_refresh_token']);
  });

  it('без хранилища (веб) — ни ошибок, ни данных', async () => {
    const cache = createOfflineCache({ storage: async () => null, owner: () => 'u1' });
    await cache.write('a', 1);
    expect(await cache.read('a')).toBeNull();
  });
});

describe('разбор — только основной карты', () => {
  const charts = (primary) => ({ charts: [{ id: 'c1', is_primary: primary === 'c1' }, { id: 'c2', is_primary: primary === 'c2' }] });

  it('сохраняется для основной и не сохраняется для другой', async () => {
    const { cache } = makeCache();
    await rememberCharts(charts('c1'), 'c1', cache);
    await rememberInterpretation('c2', [{ text: 'нет' }], cache);
    expect(await cachedInterpretation('c2', cache)).toBeNull();
    await rememberInterpretation('c1', [{ text: 'да' }], cache);
    expect(await cachedInterpretation('c1', cache)).toEqual([{ text: 'да' }]);
  });

  it('смена основной карты стирает разбор прежней', async () => {
    const { cache } = makeCache();
    await rememberCharts(charts('c1'), 'c1', cache);
    await rememberInterpretation('c1', [{ text: 'да' }], cache);
    await rememberCharts(charts('c2'), 'c2', cache);
    expect(await cache.read('interp')).toBeNull();
  });

  it('тот же список — разбор остаётся', async () => {
    const { cache } = makeCache();
    await rememberCharts(charts('c1'), 'c1', cache);
    await rememberInterpretation('c1', [{ text: 'да' }], cache);
    await rememberCharts(charts('c1'), 'c1', cache);
    expect(await cachedInterpretation('c1', cache)).toEqual([{ text: 'да' }]);
  });
});

describe('trimFeed', () => {
  const today = '2026-09-24';
  const feed = {
    horizon: { from: '2026-08-24', to: '2027-03-01', next_tier: { to: '2027-09-01', name: 'Лира' } },
    events: [
      { key: 'old', at: '2026-09-01T10:00:00+03:00', ends_at: null },
      { key: 'saturn', at: '2026-03-01T10:00:00+03:00', ends_at: '2027-01-01T10:00:00+03:00' },
      { key: 'soon', at: '2026-10-10T10:00:00+03:00', ends_at: null },
      { key: 'far', at: '2026-12-01T10:00:00+03:00', ends_at: null },
    ],
  };

  it('берёт ближайшие дни и идущие сейчас периоды', () => {
    expect(trimFeed(feed, today).events.map((e) => e.key)).toEqual(['saturn', 'soon']);
  });

  it('сужает горизонт до окна и выбрасывает next_tier', () => {
    const { horizon } = trimFeed(feed, today);
    expect(horizon).toEqual({ from: '2026-09-17', to: '2026-10-24' });
  });
});

describe('staleForecastNames', () => {
  it('дневные — раньше сегодня (прогноза на вчера нет), лунные — старше 40 дней', () => {
    const names = [
      'forecast:day:2026-09-22:c1', 'forecast:day:2026-09-23:c1', 'forecast:day:2026-09-24:c1',
      'forecast:lunation:2026-08-01:full_moon:c1', 'forecast:lunation:2026-09-10:new_moon:c1',
    ];
    expect(staleForecastNames(names, '2026-09-24')).toEqual([
      'forecast:day:2026-09-22:c1', 'forecast:day:2026-09-23:c1',
      'forecast:lunation:2026-08-01:full_moon:c1',
    ]);
  });
});
