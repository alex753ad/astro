import { describe, expect, it } from 'vitest';
import {
  MIN_DELAY_MS,
  REFRESH_BUFFER_MS,
  RETRY_BASE_MS,
  RETRY_MAX_MS,
  nextRefresh,
  retryDelay,
} from './refreshSchedule';

const NOW = 1_800_000_000_000;

function token(secondsFromNow) {
  const payload = btoa(JSON.stringify({ exp: Math.floor(NOW / 1000) + secondsFromNow }));
  return `header.${payload}.signature`;
}

describe('nextRefresh', () => {
  it('свежий токен: таймер за буфер до истечения', () => {
    const result = nextRefresh(token(15 * 60), NOW);
    expect(result.kind).toBe('later');
    expect(result.delay).toBe(15 * 60 * 1000 - REFRESH_BUFFER_MS);
  });

  it('протухший токен: обновляться сейчас, а не молчать', () => {
    // Дефект 2: раньше при delay <= 0 не ставилось НИЧЕГО и никто не узнавал.
    expect(nextRefresh(token(-1), NOW)).toEqual({ kind: 'now' });
    expect(nextRefresh(token(-3600), NOW)).toEqual({ kind: 'now' });
  });

  it('истекает раньше буфера: не сейчас, но и не мгновенным циклом', () => {
    const result = nextRefresh(token(30), NOW);
    expect(result.kind).toBe('later');
    expect(result.delay).toBe(MIN_DELAY_MS);
  });

  it('срок не прочитан — не гадаем', () => {
    expect(nextRefresh('не-jwt', NOW)).toEqual({ kind: 'never' });
    expect(nextRefresh('', NOW)).toEqual({ kind: 'never' });
  });
});

describe('retryDelay', () => {
  it('удваивается и упирается в потолок', () => {
    expect(retryDelay(0)).toBe(RETRY_BASE_MS);
    expect(retryDelay(1)).toBe(RETRY_BASE_MS * 2);
    expect(retryDelay(2)).toBe(RETRY_BASE_MS * 4);
    expect(retryDelay(20)).toBe(RETRY_MAX_MS);
  });

  it('никогда не возвращает ноль — иначе повтор станет циклом', () => {
    for (let i = 0; i < 30; i += 1) expect(retryDelay(i)).toBeGreaterThanOrEqual(RETRY_BASE_MS);
  });
});
