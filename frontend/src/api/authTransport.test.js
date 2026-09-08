/**
 * authTransport.test.js — объект плагина Capacitor не должен попадать под await.
 *
 * Дефект, ради которого написан (найден замером на устройстве 08.09.2026):
 * `preferences()` возвращала сам `Preferences` из async-функции, то есть
 * пропускала его через разворачивание thenable. `Preferences` — Proxy, чья
 * get-ловушка отдаёт вызов моста для любого имени, включая `then`; мост
 * отвечал «"Preferences.then()" is not implemented on android», а `resolve`
 * и `reject` принимал за аргументы вызова и не звал никогда. Внешний `await`
 * зависал навсегда — обновление сессии не стартовало ни по одному пути, и
 * ни один catch не срабатывал.
 *
 * ⚠️ Почему этого не ловил ни один существующий тест и почему мало было бы
 * «замокать хранилище»: session.test.js подменяет ВЕСЬ этот модуль (в среде
 * тестов нет @capacitor/preferences), а его заглушка — обычный объект без
 * `then`. Она проверяет контур обновления и по построению не может увидеть
 * дефект транспорта. DOM-окружение здесь ни при чём и не нужно: дефект
 * чисто в механике промисов, а мост подделывается тем же Proxy, что и в
 * настоящем @capacitor/core.
 *
 * Проверяется ИНВАРИАНТ, а не конкретная строка: свойство `then` у объекта
 * плагина не читается никогда. Так тест переживёт любую переделку helper'а —
 * и упадёт на любом новом месте, где плагин снова окажется под await.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

/** Тронутые имена свойств — по ним и виден запрещённый доступ к `then`. */
const touched = [];
const calls = [];
let stored = null;

/**
 * Тот же Proxy, что делает registerPlugin в @capacitor/core: любое имя
 * свойства превращается в вызов моста. Ключевое здесь — что `then` НЕ
 * исключение, ровно как в настоящем плагине.
 */
const pluginProxy = new Proxy({}, {
  get(_, prop) {
    touched.push(String(prop));
    if (prop === 'then') {
      // Мост: метода `then` у плагина нет. Настоящий отказ уходит в промис,
      // которого никто не слушает, а resolve/reject не вызываются — внешний
      // await зависает. Здесь то же самое: возвращаем функцию, которая
      // аргументы игнорирует.
      return () => Promise.reject(
        new Error('"Preferences.then()" is not implemented on android'),
      );
    }
    return async (options) => {
      calls.push([String(prop), options]);
      if (prop === 'get') return { value: stored };
      if (prop === 'set') { stored = options.value; return {}; }
      if (prop === 'remove') { stored = null; return {}; }
      return {};
    };
  },
});

vi.mock('@capacitor/preferences', () => ({ Preferences: pluginProxy }));

/** Свежий импорт: IS_MOBILE вычисляется на уровне модуля. */
async function freshTransport() {
  vi.resetModules();
  vi.stubEnv('VITE_MOBILE', 'true');
  return import('./authTransport');
}

/**
 * Зависание — тоже провал, но по таймауту оно выглядит как сломанный тест, а
 * не как найденный дефект. Гонка с коротким таймером превращает его во
 * внятное «повисло».
 */
function within(promise, ms = 200) {
  return Promise.race([
    promise,
    new Promise((resolve) => setTimeout(() => resolve('ПОВИСЛО'), ms)),
  ]);
}

beforeEach(() => {
  touched.length = 0;
  calls.length = 0;
  stored = null;
  vi.spyOn(console, 'log').mockImplementation(() => {});
  vi.spyOn(console, 'warn').mockImplementation(() => {});
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
});

describe('нативное хранилище refresh-токена', () => {
  it('читает токен, не трогая `then` у объекта плагина', async () => {
    stored = 'refresh-abc';
    const { readRefreshToken } = await freshTransport();

    await expect(within(readRefreshToken())).resolves.toBe('refresh-abc');
    expect(touched).not.toContain('then');
    expect(calls).toContainEqual(['get', { key: 'astro_refresh_native' }]);
  });

  it('пишет токен, не трогая `then` у объекта плагина', async () => {
    const { rememberRefreshToken, readRefreshToken } = await freshTransport();

    await expect(
      within(rememberRefreshToken({ refresh_token: 'refresh-xyz' })),
    ).resolves.toBe(true);
    expect(touched).not.toContain('then');
    await expect(within(readRefreshToken())).resolves.toBe('refresh-xyz');
  });

  it('удаляет токен, не трогая `then` у объекта плагина', async () => {
    stored = 'refresh-abc';
    const { forgetRefreshToken, readRefreshToken } = await freshTransport();

    await expect(within(forgetRefreshToken())).resolves.toBeUndefined();
    expect(touched).not.toContain('then');
    await expect(within(readRefreshToken())).resolves.toBeNull();
  });

  it('тело запроса обновления содержит сохранённый токен', async () => {
    stored = 'refresh-abc';
    const { authRequestBody } = await freshTransport();

    await expect(within(authRequestBody())).resolves.toBe(
      JSON.stringify({ refresh_token: 'refresh-abc' }),
    );
  });
});
