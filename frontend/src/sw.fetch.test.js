// sw.js не должен трогать не-http(s) запросы: Cache API их не принимает,
// cache.put на chrome-extension: бросает TypeError в консоль.
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';
import { describe, expect, it } from 'vitest';

const SRC = readFileSync(fileURLToPath(new URL('../public/sw.js', import.meta.url)), 'utf8');

function fetchEvent(url) {
  const handlers = {};
  const caches = { match: async () => new Response('x'), open: async () => ({ put: async () => {} }) };
  vm.runInNewContext(SRC, { self: { addEventListener: (t, fn) => { handlers[t] = fn; } }, URL, caches, Response });
  let responded = false;
  handlers.fetch({ request: { url, method: 'GET', mode: 'no-cors' }, respondWith: () => { responded = true; } });
  return responded;
}

describe('sw.js fetch', () => {
  it('chrome-extension: — мимо воркера', () => {
    expect(fetchEvent('chrome-extension://abc/script.js')).toBe(false);
  });

  it('https-статика — через воркер', () => {
    expect(fetchEvent('https://aristeatime.ru/assets/app.js')).toBe(true);
  });
});
