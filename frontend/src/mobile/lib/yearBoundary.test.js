/**
 * Смена года и 29 февраля на клиенте: «сегодня», прогнозные дни, сдвиг дат.
 * Прогон идёт в двух поясах (package.json: TZ=UTC и TZ=Europe/Moscow) —
 * по Москве Новый год наступает в 21:00 UTC, и ожидание считается от пояса.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { localToday, shiftDays } from './feedTime';
import { forecastDates } from './feedAnchor';
import { _resetServerClock } from '../../lib/serverClock';

afterEach(() => {
  vi.useRealTimers();
  _resetServerClock(0);
});

describe('прогнозные дни через Новый год и 29 февраля', () => {
  it('31.12 в 23:30 открыты 30.12, 31.12 и 01.01', () => {
    expect(forecastDates('2026-12-31', 23)).toEqual(['2026-12-30', '2026-12-31', '2027-01-01']);
  });
  it('01.01 в 00:30 — вчера 31.12, завтра ещё закрыт', () => {
    expect(forecastDates('2027-01-01', 0)).toEqual(['2026-12-31', '2027-01-01']);
  });
  it('високосный февраль', () => {
    expect(forecastDates('2028-02-28', 20)).toEqual(['2028-02-27', '2028-02-28', '2028-02-29']);
    expect(forecastDates('2028-02-29', 20)).toEqual(['2028-02-28', '2028-02-29', '2028-03-01']);
    expect(shiftDays('2028-03-01', -1)).toBe('2028-02-29');
    expect(shiftDays('2027-03-01', -1)).toBe('2027-02-28');
  });
});

describe('«сегодня» в новогоднюю ночь', () => {
  it('00:30 по Москве = 21:30 UTC 31.12: дата — по поясу устройства, момент — по серверу', () => {
    const moment = Date.UTC(2026, 11, 31, 21, 30);
    vi.useFakeTimers({ now: moment });
    const d = new Date(moment);
    const pad = (n) => String(n).padStart(2, '0');
    const expected = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
    expect(localToday()).toBe(expected);
    if (process.env.TZ === 'Europe/Moscow') expect(expected).toBe('2027-01-01');
  });

  it('часы телефона ушли на год вперёд — «сегодня» остаётся серверным', () => {
    const server = Date.UTC(2026, 11, 31, 12, 0);
    vi.useFakeTimers({ now: server + 365 * 24 * 3600 * 1000 });
    _resetServerClock(-365 * 24 * 3600 * 1000);
    expect(localToday().startsWith('2026-12-31')).toBe(true);
  });
});
