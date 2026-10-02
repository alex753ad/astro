/**
 * widgetSync.test.js — когда приложение кладёт запас виджету и когда снимает
 * его (флаг widget).
 *
 * Плагин подделан Proxy, который на ЛЮБОЕ имя, включая `then`, отдаёт
 * функцию (приём api/authTransport.test.js): если код вернёт или await-нет
 * объект плагина, вызов повиснет и тест упадёт по гонке, а не пройдёт.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_MS, _resetForTests, applyWidget, signOutWidget, widgetDiagLine } from './widgetSync';

function fakePlugin() {
  const calls = [];
  const impl = {
    save: async (a) => { calls.push(['save', a.data]); },
    status: async () => ({ component: 1, listed: true, placed: 0, days: 14, today: true, pin: true }),
  };
  const plugin = new Proxy({}, { get: (_, name) => impl[name] || (() => new Promise(() => {})) });
  return { plugin, calls };
}

const DAYS = [{ date: '2026-10-02', title: '15:01 · Луна к твоей Венере' }];
const okFetch = () => vi.fn(async () => ({ ok: true, json: async () => ({ days: DAYS }) }));
const race = (p) => Promise.race([p, new Promise((_, r) => setTimeout(() => r(new Error('ПОВИСЛО')), 500))]);
const at = (iso) => new Date(iso);

beforeEach(() => _resetForTests());

describe('флаг выключен', () => {
  it('стирает запас (на виджете фаза Луны), компонент не трогает, на сервер не ходит', async () => {
    const { plugin, calls } = fakePlugin();
    const fetcher = okFetch();
    await race(applyWidget(false, true, { plugin, fetcher }));
    expect(calls).toEqual([['save', '']]);
    expect(fetcher).not.toHaveBeenCalled();
  });
});

describe('флаг включён', () => {
  it('вошли — кладёт дни из /widget', async () => {
    const { plugin, calls } = fakePlugin();
    const fetcher = okFetch();
    await race(applyWidget(true, true, { plugin, fetcher, now: at('2026-10-02T10:00:00') }));
    expect(fetcher.mock.calls[0][0]).toMatch(/\/widget$/);
    expect(calls).toEqual([['save', JSON.stringify({ days: DAYS })]]);
  });

  it('повтор в те же сутки раньше REFRESH_MS — без запроса; новые сутки — с запросом', async () => {
    const { plugin } = fakePlugin();
    const fetcher = okFetch();
    await applyWidget(true, true, { plugin, fetcher, now: at('2026-10-02T10:00:00') });
    await applyWidget(true, true, { plugin, fetcher, now: at('2026-10-02T11:00:00') });
    expect(fetcher).toHaveBeenCalledTimes(1);
    await applyWidget(true, true, { plugin, fetcher, now: new Date(at('2026-10-02T10:00:00').getTime() + REFRESH_MS) });
    expect(fetcher).toHaveBeenCalledTimes(2);
    await applyWidget(true, true, { plugin, fetcher, now: at('2026-10-03T00:30:00') });
    expect(fetcher).toHaveBeenCalledTimes(3);
  });

  it('не вошли — «войди», без запроса', async () => {
    const { plugin, calls } = fakePlugin();
    const fetcher = okFetch();
    await race(applyWidget(true, false, { plugin, fetcher }));
    expect(calls).toEqual([['save', JSON.stringify({ signedOut: true })]]);
    expect(fetcher).not.toHaveBeenCalled();
  });

  it('сервер отказал — прежний запас не трогается', async () => {
    const { plugin, calls } = fakePlugin();
    const fetcher = vi.fn(async () => ({ ok: false }));
    await race(applyWidget(true, true, { plugin, fetcher }));
    expect(calls).toEqual([]);
  });

  it('сеть упала — без исключения наружу', async () => {
    const { plugin } = fakePlugin();
    const fetcher = vi.fn(async () => { throw new TypeError('Failed to fetch'); });
    await expect(race(applyWidget(true, true, { plugin, fetcher }))).resolves.toBeUndefined();
  });
});

describe('выход из аккаунта', () => {
  it('без флага — не пишет «войди»: там и так фаза Луны', async () => {
    const { plugin, calls } = fakePlugin();
    await applyWidget(false, true, { plugin });
    signOutWidget(plugin);
    await Promise.resolve();
    expect(calls).toEqual([['save', '']]);
  });

  it('чужой день стирается сразу, следующий вход запрашивает заново', async () => {
    const { plugin, calls } = fakePlugin();
    const fetcher = okFetch();
    await applyWidget(true, true, { plugin, fetcher, now: at('2026-10-02T10:00:00') });
    signOutWidget(plugin);
    await Promise.resolve();
    expect(calls.at(-1)).toEqual(['save', JSON.stringify({ signedOut: true })]);
    await applyWidget(true, true, { plugin, fetcher, now: at('2026-10-02T10:05:00') });
    expect(fetcher).toHaveBeenCalledTimes(2);
  });
});

describe('очередь ответов /flags', () => {
  it('ответ во время идущего не теряется: применяется последний', async () => {
    const { plugin, calls } = fakePlugin();
    const fetcher = okFetch();
    const first = applyWidget(false, true, { plugin, fetcher });
    const second = applyWidget(true, true, { plugin, fetcher, now: at('2026-10-02T10:00:00') });
    await race(Promise.all([first, second]));
    expect(calls.map((c) => c[0])).toEqual(['save', 'save']);
    expect(calls.at(-1)).toEqual(['save', JSON.stringify({ days: DAYS })]);
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
});

describe('строка диагностики', () => {
  it('до ответа /flags — так и пишет', async () => {
    const { plugin } = fakePlugin();
    expect(await race(widgetDiagLine(plugin))).toMatch(/^Виджет: нет ответа \/flags · компонент вкл · в списке да/);
  });

  it('отказ /widget виден, а не проглочен', async () => {
    const { plugin } = fakePlugin();
    await applyWidget(true, true, { plugin, fetcher: vi.fn(async () => ({ ok: false, status: 404 })) });
    expect(await widgetDiagLine(plugin)).toMatch(/флаг вкл .* шаг: \/widget ответил 404/);
  });

  it('ошибка плагина — с шагом, на котором упало', async () => {
    const plugin = new Proxy({}, { get: (_, name) => (name === 'save'
      ? async () => { throw new Error('not implemented') } : async () => ({})) });
    await applyWidget(true, true, { plugin, fetcher: okFetch() });
    const line = await widgetDiagLine(null);
    expect(line).toMatch(/ошибка на шаге «запрос \/widget»: not implemented/);
    expect(line).toMatch(/плагин недоступен/);
  });
});
