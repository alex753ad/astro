import { beforeEach, describe, expect, it, vi } from 'vitest';
import { syncDeviceTimezone, withTz } from './deviceTimezone';

const store = new Map();
beforeEach(() => {
  store.clear();
  globalThis.localStorage = {
    getItem: (k) => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => store.set(k, String(v)),
  };
});

describe('withTz', () => {
  it('добавляет параметр к адресу с запросом и без', () => {
    expect(withTz('/push/upcoming', 'Asia/Novosibirsk')).toBe('/push/upcoming?tz=Asia%2FNovosibirsk');
    expect(withTz('/feed?from_date=1', 'Europe/Moscow')).toBe('/feed?from_date=1&tz=Europe%2FMoscow');
    expect(withTz('/feed', '')).toBe('/feed');
  });
});

describe('syncDeviceTimezone', () => {
  it('шлёт один раз на пару «пользователь + пояс»', async () => {
    const patch = vi.fn(async () => true);
    expect(await syncDeviceTimezone('u1', patch, 'Asia/Novosibirsk')).toBe(true);
    expect(await syncDeviceTimezone('u1', patch, 'Asia/Novosibirsk')).toBe(false);
    expect(patch).toHaveBeenCalledTimes(1);
    expect(patch).toHaveBeenCalledWith({ timezone: 'Asia/Novosibirsk' });
  });

  it('сменился пояс или пользователь — шлёт снова', async () => {
    const patch = vi.fn(async () => true);
    await syncDeviceTimezone('u1', patch, 'Europe/Moscow');
    await syncDeviceTimezone('u1', patch, 'Asia/Tokyo');
    await syncDeviceTimezone('u2', patch, 'Asia/Tokyo');
    expect(patch).toHaveBeenCalledTimes(3);
  });

  it('неудача не запоминается — повторим при следующем входе', async () => {
    const fail = vi.fn(async () => false);
    await syncDeviceTimezone('u1', fail, 'Europe/Moscow');
    const ok = vi.fn(async () => true);
    expect(await syncDeviceTimezone('u1', ok, 'Europe/Moscow')).toBe(true);
  });

  it('сбой сети не бросает наружу', async () => {
    const boom = vi.fn(async () => { throw new TypeError('Failed to fetch'); });
    expect(await syncDeviceTimezone('u1', boom, 'Europe/Moscow')).toBe(false);
  });
});
