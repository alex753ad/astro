/**
 * widgetPin.test.js — когда предлагать поставить виджет и что считать
 * добавлением (решения владельца 02.10.2026, docs/widget_pin_card_plan.md).
 *
 * Плагин подделан thenable-Proxy (приём api/authTransport.test.js): если код
 * вернёт или await-нет объект плагина, вызов повиснет и тест упадёт по гонке.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const posted = [];
const seen = [];
vi.mock('../../config', () => ({ API_BASE: '/api/v1' }));
vi.mock('../../api/client', () => ({
  authFetch: vi.fn(async (url, opts) => { posted.push(JSON.parse(opts.body)); return { ok: true }; }),
}));
vi.mock('./firstWeek', () => ({ markSeen: (k) => seen.push(k) }));

const {
  MAX_DISMISSALS, MIN_OPEN_DAYS, cardAllowed, checkPlaced, countOpenDay, dismiss, logShown, pin, readState,
} = await import('./widgetPin');

function fakePlugin(status) {
  const calls = [];
  const impl = {
    status: async () => status,
    requestPin: async () => { calls.push('requestPin'); return { shown: true }; },
  };
  return { calls, plugin: new Proxy({}, { get: (_, n) => impl[n] || (() => new Promise(() => {})) }) };
}
const race = (p) => Promise.race([p, new Promise((_, r) => setTimeout(() => r(new Error('ПОВИСЛО')), 500))]);
const OK = { flag: true, firstWeek: false, pin: true, placed: 0, weekAhead: false };

beforeEach(() => {
  posted.length = 0;
  seen.length = 0;
  const store = new Map();
  vi.stubGlobal('localStorage', {
    getItem: (k) => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => { store.set(k, String(v)); },
  });
});

function openDays(n) {
  for (let i = 1; i <= n; i += 1) countOpenDay(`2026-10-0${i}`);
}

describe('карточка в ленте: кому и когда', () => {
  it(`с ${MIN_OPEN_DAYS}-го дня открытия приложения`, () => {
    openDays(MIN_OPEN_DAYS - 1);
    countOpenDay('2026-10-02'); // тот же день дважды — один день
    expect(cardAllowed(readState(), '2026-10-02', OK)).toBe(false);
    openDays(MIN_OPEN_DAYS);
    expect(cardAllowed(readState(), '2026-10-03', OK)).toBe(true);
  });

  it.each([
    ['флаг выключен', { flag: false }],
    ['ответа /flags не было', { flag: null }],
    ['идёт первая неделя — её роль играет день 3', { firstWeek: true }],
    ['неизвестно, идёт ли первая неделя', { firstWeek: null }],
    ['лаунчер не умеет закреплять', { pin: false }],
    ['виджет уже на экране', { placed: 1 }],
    ['стоит карточка «Недели вперёд»', { weekAhead: true }],
  ])('не показывается: %s', (_, over) => {
    openDays(MIN_OPEN_DAYS);
    expect(cardAllowed(readState(), '2026-10-03', { ...OK, ...over })).toBe(false);
  });

  it('«Не сейчас» — на 14 дней, второй раз — никогда', () => {
    openDays(MIN_OPEN_DAYS);
    dismiss('2026-10-03');
    expect(cardAllowed(readState(), '2026-10-16', OK)).toBe(false);
    expect(cardAllowed(readState(), '2026-10-17', OK)).toBe(true);
    dismiss('2026-10-17');
    expect(readState().dismissals).toBe(MAX_DISMISSALS);
    expect(cardAllowed(readState(), '2027-01-01', OK)).toBe(false);
  });
});

describe('запрос и проверка «виджет на экране»', () => {
  it('pin зовёт системный запрос и не виснет на объекте плагина', async () => {
    const { plugin, calls } = fakePlugin({ placed: 0, pin: true });
    expect(await race(pin('card', { plugin }))).toBe(true);
    expect(calls).toEqual(['requestPin']);
    expect(readState().pending).toBe('card');
  });

  it('добавили после карточки — «добавление» с источником один раз, пункт недели закрыт', async () => {
    const { plugin } = fakePlugin({ placed: 1, pin: true });
    await pin('card', { plugin });
    await race(checkPlaced({ plugin }));
    await checkPlaced({ plugin });
    expect(posted).toEqual([{ kind: 'added', source: 'card' }]);
    expect(seen).toContain('widget');
  });

  it('поставили сами — источник manual', async () => {
    await checkPlaced(fakePlugin({ placed: 1, pin: true }));
    expect(posted).toEqual([{ kind: 'added', source: 'manual' }]);
  });

  it('нажали «Добавить» в карточке, а виджета нет — как «Не сейчас»', async () => {
    const { plugin } = fakePlugin({ placed: 0, pin: true });
    await pin('card', { plugin });
    await checkPlaced({ plugin }, '2026-10-05');
    expect(readState()).toMatchObject({ dismissals: 1, until: '2026-10-19', pending: '' });
  });

  it('из первой недели без добавления — карточка недели остаётся, отказом не считается', async () => {
    const { plugin } = fakePlugin({ placed: 0, pin: true });
    await pin('first_week', { plugin });
    await checkPlaced({ plugin });
    expect(readState().dismissals).toBe(0);
    expect(seen).toEqual([]);
  });

  it('лаунчер не умеет закреплять — пункт недели закрыт сразу', async () => {
    await checkPlaced(fakePlugin({ placed: 0, pin: false }));
    expect(seen).toEqual(['widget']);
  });

  it('показ — в сводку раз в сутки на источник', () => {
    logShown('card', '2026-10-05');
    logShown('card', '2026-10-05');
    logShown('first_week', '2026-10-05');
    logShown('card', '2026-10-06');
    expect(posted).toEqual([
      { kind: 'shown', source: 'card' }, { kind: 'shown', source: 'first_week' }, { kind: 'shown', source: 'card' },
    ]);
  });
});
