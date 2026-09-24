import { afterEach, describe, expect, it, vi } from 'vitest';
import { _resetServerClock, noteFreshToken, serverNow } from './serverClock';
import { isTokenExpired } from './jwt';
import { nextRefresh } from './refreshSchedule';

function token(payload) {
  return `h.${btoa(JSON.stringify(payload))}.s`;
}

const SERVER_NOW = Date.UTC(2026, 11, 31, 20, 30); // 31.12.2026 23:30 МСК
const HOUR = 60 * 60 * 1000;

afterEach(() => {
  vi.useRealTimers();
  _resetServerClock(0);
});

describe('часы телефона спешат на час', () => {
  // Свежий токен: выдан сейчас по серверу, живёт 15 минут.
  const fresh = token({ iat: SERVER_NOW / 1000, exp: SERVER_NOW / 1000 + 15 * 60 });

  it('без поправки свежий токен выглядит протухшим — это и был цикл обновлений', () => {
    vi.useFakeTimers({ now: SERVER_NOW + HOUR });
    expect(isTokenExpired(fresh)).toBe(true);
    expect(nextRefresh(fresh).kind).toBe('now');
  });

  it('после отметки свежего токена срок считается по серверу', () => {
    vi.useFakeTimers({ now: SERVER_NOW + HOUR });
    noteFreshToken(fresh);
    expect(Math.abs(serverNow() - SERVER_NOW)).toBeLessThan(1000);
    expect(isTokenExpired(fresh)).toBe(false);
    const next = nextRefresh(fresh);
    expect(next.kind).toBe('later');
    expect(next.delay).toBe(13 * 60 * 1000);
  });

  it('«сегодня» — серверная дата: на телефоне уже 2027 год, а на сервере ещё нет', () => {
    // Телефон спешит на сутки: у него 01.01.2028, по серверу — 31.12.2026 23:30 МСК.
    vi.useFakeTimers({ now: SERVER_NOW + 366 * 24 * HOUR });
    noteFreshToken(fresh);
    const d = new Date(serverNow());
    expect(d.getUTCFullYear()).toBe(2026);
  });
});

describe('шум сети не считается расхождением', () => {
  it('разница в пару секунд даёт ноль', () => {
    vi.useFakeTimers({ now: SERVER_NOW + 2000 });
    noteFreshToken(token({ iat: SERVER_NOW / 1000, exp: SERVER_NOW / 1000 + 900 }));
    expect(serverNow()).toBe(SERVER_NOW + 2000);
  });

  it('токен без iat ничего не меняет', () => {
    _resetServerClock(12345);
    noteFreshToken(token({ exp: 1 }));
    vi.useFakeTimers({ now: SERVER_NOW });
    expect(serverNow()).toBe(SERVER_NOW + 12345);
  });
});
