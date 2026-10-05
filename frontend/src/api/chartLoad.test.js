/**
 * chartLoad.test.js — загрузка карты на ChartPage с протухшим access-токеном.
 *
 * До 05.10.2026 ChartPage грузил карту голым fetch: через 15 минут токен
 * протухал, сервер отвечал 401, обновления не было — вошедший видел «Карта не
 * найдена» на своей карте. Теперь — fetchChart поверх authFetch.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const ACCESS_KEY = 'astro_access_token';

vi.mock('./authTransport', () => ({
  IS_MOBILE: false,
  AUTH_CREDENTIALS: 'include',
  MOBILE_CLIENT_HEADER: 'X-Client-Platform',
  clientHeaders: () => ({}),
  authRequestBody: async () => JSON.stringify({}),
  readRefreshToken: async () => null,
  rememberRefreshToken: async () => {},
  forgetRefreshToken: async () => {},
}));

function stubStorage(name, initial = {}) {
  const store = new Map(Object.entries(initial));
  vi.stubGlobal(name, {
    getItem: (k) => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => store.set(k, String(v)),
    removeItem: (k) => store.delete(k),
  });
}

function jwt(secondsFromNow) {
  const payload = btoa(JSON.stringify({ exp: Math.floor(Date.now() / 1000) + secondsFromNow }));
  return `header.${payload}.signature`;
}

const FRESH = jwt(900);
const CHART = { id: 'c1', name: 'Тест' };

/** Сервер: карта отдаётся только со свежим токеном, иначе 401. */
function stubServer() {
  const calls = [];
  vi.stubGlobal('fetch', vi.fn(async (url, opts = {}) => {
    calls.push(String(url));
    if (String(url).endsWith('/auth/refresh')) {
      return { ok: true, status: 200, json: async () => ({ access_token: FRESH }) };
    }
    const ok = opts.headers?.Authorization === `Bearer ${FRESH}`;
    return { ok, status: ok ? 200 : 401, json: async () => (ok ? CHART : { detail: 'expired' }) };
  }));
  return calls;
}

beforeEach(() => {
  stubStorage('sessionStorage');
  vi.resetModules();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('fetchChart с протухшим токеном', () => {
  it('срок истёк по exp — обновляется до запроса, карта загружается', async () => {
    stubStorage('localStorage', { [ACCESS_KEY]: jwt(-60) });
    const calls = stubServer();
    const { fetchChart } = await import('./client');

    const resp = await fetchChart('c1');

    expect(resp.ok).toBe(true);
    expect(await resp.json()).toEqual(CHART);
    expect(calls.filter((u) => u.endsWith('/auth/refresh'))).toHaveLength(1);
  });

  it('сервер ответил 401 (часы разошлись) — обновление и повтор, карта загружается', async () => {
    stubStorage('localStorage', { [ACCESS_KEY]: jwt(600) });
    const calls = stubServer();
    const { fetchChart } = await import('./client');

    const resp = await fetchChart('c1');

    expect(resp.ok).toBe(true);
    expect(await resp.json()).toEqual(CHART);
    expect(calls.filter((u) => u.includes('/chart/c1'))).toHaveLength(2);
  });
});
