// sw.js обязан показывать уведомление на КАЖДЫЙ пуш — даже пустой или битый:
// Safari отзывает подписку после молчаливых пушей (см. комментарий в sw.js).
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';
import { describe, expect, it } from 'vitest';

const SRC = readFileSync(fileURLToPath(new URL('../public/sw.js', import.meta.url)), 'utf8');

async function push(data) {
  const handlers = {};
  const shown = [];
  const self = {
    addEventListener: (type, fn) => { handlers[type] = fn; },
    registration: { showNotification: async (title, opts) => { shown.push({ title, ...opts }); } },
  };
  vm.runInNewContext(SRC, { self, URL });
  let pending;
  handlers.push({ data, waitUntil: (p) => { pending = p; } });
  await pending;
  return shown;
}

const text = (s) => ({ json: () => JSON.parse(s), text: () => s });

describe('sw.js push', () => {
  it('без данных — показывает запасной текст', async () => {
    const shown = await push(null);
    expect(shown).toHaveLength(1);
    expect(shown[0].title).toBe('Aristea');
    expect(shown[0].body).toMatch(/тебя/);
  });

  it('пустой JSON — тоже показывает', async () => {
    const shown = await push(text('{}'));
    expect(shown).toHaveLength(1);
    expect(shown[0].body).toBeTruthy();
  });

  it('не JSON — показывает текст как есть', async () => {
    const shown = await push(text('привет'));
    expect(shown[0].body).toBe('привет');
  });

  it('обычный пуш — свои заголовок, текст и ссылка', async () => {
    const shown = await push(text(JSON.stringify({ title: 'T', body: 'B', url: '/x' })));
    expect(shown[0]).toMatchObject({ title: 'T', body: 'B', data: { url: '/x' } });
  });
});
