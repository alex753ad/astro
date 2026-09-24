/**
 * forecastApi.test.js — адреса запросов прогнозов и то, к какой фазе
 * относится событие ленты.
 *
 * Транспорт подменяется целиком (тот же приём, что в chartApi.test.js):
 * настоящий тянет @capacitor/preferences, которого в тестовой среде нет.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { hasLunationForecast, lunationPhase } from './lunationPhase';

const calls = [];
vi.mock('./authFetchTimeout', () => ({
  REQUEST_TIMEOUT_MS: 15000,
  getWithRetry: (url) => {
    calls.push(url);
    return Promise.resolve({ ok: true, status: 200, json: async () => ({}) });
  },
  failWith: async () => { throw new Error('отказ'); },
}));

const { fetchLunationForecast, fetchDayForecast } = await import('./forecastApi');

beforeEach(() => { calls.length = 0; });

describe('прогноз на день', () => {
  it('дата и пояс телефона уходят в запрос', async () => {
    await fetchDayForecast('c1', '2026-09-25', 'Asia/Novosibirsk');
    expect(calls[0]).toMatch(/\/chart\/c1\/forecast\/day\?date=2026-09-25&tz=Asia%2FNovosibirsk$/);
  });

  it('без пояса — запрос без tz (сервер возьмёт пояс карты)', async () => {
    await fetchDayForecast('c1', '2026-09-24', '');
    expect(calls[0]).toMatch(/\/forecast\/day\?date=2026-09-24$/);
  });
});

describe('прогноз на фазу', () => {
  it('фаза и местная дата берутся из события ленты', async () => {
    const event = { kind: 'moon_phase', at: '2026-10-10T06:49:00+03:00', meta: { type: 'new_moon' } };
    await fetchLunationForecast('c1', event, 'Europe/Moscow');
    expect(calls[0]).toContain('/chart/c1/forecast/lunation?phase=new_moon&date=2026-10-10&tz=Europe%2FMoscow');
  });

  it('затмение ведёт к прогнозу своей фазы', async () => {
    const event = { kind: 'eclipse', at: '2027-02-06T19:00:00+03:00', meta: { type: 'solar' } };
    await fetchLunationForecast('c1', event, '');
    expect(calls[0]).toContain('phase=new_moon&date=2027-02-06');
  });
});

describe('lunationPhase', () => {
  it.each([
    [{ kind: 'moon_phase', meta: { type: 'new_moon' } }, 'new_moon'],
    [{ kind: 'moon_phase', meta: { type: 'full_moon' } }, 'full_moon'],
    [{ kind: 'eclipse', meta: { type: 'solar' } }, 'new_moon'],
    [{ kind: 'eclipse', meta: { type: 'lunar' } }, 'full_moon'],
    [{ kind: 'transit', meta: {} }, null],
    [{ kind: 'moon_phase' }, null],
  ])('%j → %s', (event, phase) => {
    expect(lunationPhase(event)).toBe(phase);
    expect(hasLunationForecast(event)).toBe(phase !== null);
  });
});
