/**
 * onboardingFlags.test.js — поведение флагов «видел / не видел»
 * (SPEC_ONBOARDING.md §6, §7).
 *
 * Проверяется то, что на устройстве проверить дорого и легко пропустить
 * глазами: недоступное хранилище и требование «флаг ставится только по
 * завершению». Пункты 3, 4 и 6 чек-листа приёмки §14 опираются именно на
 * эту логику.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const KEY = 'aristea.onboarding.seen';

/** Модуль держит дубль флагов в памяти процесса, поэтому каждому тесту
 * нужен свежий импорт — иначе память протекает между случаями. */
async function freshModule() {
  vi.resetModules();
  return import('./onboardingFlags');
}

/** Подменяет localStorage на рабочий или на бросающий исключение. */
function installStorage({ broken = false } = {}) {
  const store = new Map();
  const throwing = () => { throw new Error('localStorage недоступен'); };
  const stub = broken
    ? { getItem: throwing, setItem: throwing, removeItem: throwing }
    : {
      getItem: (k) => (store.has(k) ? store.get(k) : null),
      setItem: (k, v) => store.set(k, String(v)),
      removeItem: (k) => store.delete(k),
    };
  vi.stubGlobal('localStorage', stub);
  return store;
}

beforeEach(() => { installStorage(); });
afterEach(() => { vi.unstubAllGlobals(); });

describe('рабочее хранилище', () => {
  it('до первого показа флага нет', async () => {
    const { isSeen } = await freshModule();
    expect(isSeen(KEY)).toBe(false);
  });

  it('markSeen переживает перезапуск приложения', async () => {
    const store = installStorage();
    const first = await freshModule();
    first.markSeen(KEY);

    // Новый импорт = новый запуск: память сброшена, хранилище то же.
    const second = await freshModule();
    vi.stubGlobal('localStorage', {
      getItem: (k) => (store.has(k) ? store.get(k) : null),
      setItem: (k, v) => store.set(k, String(v)),
      removeItem: (k) => store.delete(k),
    });
    expect(second.isSeen(KEY)).toBe(true);
  });

  it('ключи экранов раздельные: «Лента» не гасит «Карту»', async () => {
    // Приложение открывается на «Ленте», и до «Карты» человек может не
    // дойти вовсе — общий ключ погасил бы подсказки невиденного экрана.
    const { isSeen, markSeen, HINTS_KEYS } = await freshModule();
    markSeen(HINTS_KEYS.feed);
    expect(isSeen(HINTS_KEYS.feed)).toBe(true);
    expect(isSeen(HINTS_KEYS.chart)).toBe(false);
  });

  it('чужое значение в ключе значит «не видел», а не «видел»', async () => {
    // Мусор или старый формат обязан приводить к лишнему показу, а не к
    // потере единственного.
    const { isSeen } = await freshModule();
    localStorage.setItem(KEY, 'true');
    expect(isSeen(KEY)).toBe(false);
    localStorage.setItem(KEY, '1');
    expect(isSeen(KEY)).toBe(true);
  });
});

describe('недоступное хранилище не блокирует интерфейс', () => {
  it('isSeen не бросает и отвечает «не видел»', async () => {
    installStorage({ broken: true });
    const { isSeen } = await freshModule();
    expect(() => isSeen(KEY)).not.toThrow();
    expect(isSeen(KEY)).toBe(false);
  });

  it('markSeen не бросает', async () => {
    installStorage({ broken: true });
    const { markSeen } = await freshModule();
    expect(() => markSeen(KEY)).not.toThrow();
  });

  it('в рамках одного запуска повтора нет — держит память', async () => {
    // Записать «видел» некуда, но показывать второй раз подряд нельзя.
    installStorage({ broken: true });
    const { isSeen, markSeen } = await freshModule();
    markSeen(KEY);
    expect(isSeen(KEY)).toBe(true);
  });

  it('при следующем запуске показывается снова — это и есть плата', async () => {
    installStorage({ broken: true });
    const first = await freshModule();
    first.markSeen(KEY);

    installStorage({ broken: true });
    const second = await freshModule();
    expect(second.isSeen(KEY)).toBe(false);
  });
});
