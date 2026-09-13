/**
 * localNotifications.test.js — тот же замок, что и в `api/authTransport.test.js`,
 * но на втором плагине Capacitor: объект плагина не должен попадать под await.
 *
 * Зачем копия. Дефект принадлежит не `Preferences`, а `registerPlugin`: ЛЮБОЙ
 * объект плагина — Proxy, чья get-ловушка отдаёт вызов моста для любого имени,
 * включая `then`, то есть является thenable. `return LocalNotifications` из
 * async-функции пропустил бы его через разворачивание thenable, мост принял бы
 * `then` за имя метода, а `resolve`/`reject` за аргументы вызова и не позвал бы
 * никогда. Получается не отказ, а ВЕЧНОЕ ЗАВИСАНИЕ мимо catch и мимо finally —
 * в `Preferences` это стоило четырёх дней разбора (docs/HISTORY-mobile.md).
 * Правило записано в CLAUDE.md, но записи мало: соблюдение проверяется здесь.
 *
 * Проверяется ИНВАРИАНТ, а не конкретная строка — свойство `then` не читается
 * ни в одной операции. Так тест переживёт переделку файла и упадёт на любом
 * новом месте, где плагин снова окажется под await.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const touched = [];
const calls = [];
let permission = 'granted';
let pending = [];

/** Тот же Proxy, что делает registerPlugin: `then` — НЕ исключение. */
const pluginProxy = new Proxy({}, {
  get(_, prop) {
    touched.push(String(prop));
    if (prop === 'then') {
      return () => Promise.reject(
        new Error('"LocalNotifications.then()" is not implemented on android'),
      );
    }
    return async (options) => {
      calls.push([String(prop), options]);
      if (prop === 'checkPermissions' || prop === 'requestPermissions') return { display: permission };
      if (prop === 'getPending') return { notifications: pending };
      return {};
    };
  },
});

vi.mock('@capacitor/local-notifications', () => ({ LocalNotifications: pluginProxy }));

/** Свежий импорт: IS_MOBILE вычисляется на уровне модуля. */
async function fresh() {
  vi.resetModules();
  vi.stubEnv('VITE_MOBILE', 'true');
  return import('./localNotifications');
}

/** Зависание по таймауту выглядит как сломанный тест — гонка превращает его во внятное «ПОВИСЛО». */
function within(promise, ms = 200) {
  return Promise.race([
    promise,
    new Promise((resolve) => setTimeout(() => resolve('ПОВИСЛО'), ms)),
  ]);
}

const EVENTS = [
  { key: 'transit:a:2026-09-14', kind: 'transit', at: '2026-09-14T08:00:00+03:00',
    title: '♄ Сатурн в квадрате к Солнцу', body: 'Проверка на прочность.', url: '/planner' },
  { key: 'moon:full_moon:2026-09-14', kind: 'moon', at: '2026-09-14T08:00:00+03:00',
    title: '🌕 Полнолуние завтра', body: 'Загляните в лунный календарь.', url: '/lunar' },
];
const NOW = Date.parse('2026-09-13T05:00:00+03:00');

beforeEach(() => {
  touched.length = 0;
  calls.length = 0;
  permission = 'granted';
  pending = [];
  vi.spyOn(console, 'warn').mockImplementation(() => {});
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
});

describe('объект плагина не попадает под await', () => {
  it('проверка разрешения не трогает `then`', async () => {
    const { permissionState } = await fresh();
    await expect(within(permissionState())).resolves.toBe('granted');
    expect(touched).not.toContain('then');
  });

  it('запрос разрешения не трогает `then`', async () => {
    const { requestPermission } = await fresh();
    await expect(within(requestPermission())).resolves.toBe('granted');
    expect(touched).not.toContain('then');
  });

  it('создание канала не трогает `then`', async () => {
    const { ensureChannel } = await fresh();
    await within(ensureChannel());
    expect(touched).not.toContain('then');
  });

  it('отмена не трогает `then`', async () => {
    pending = [{ id: 1 }, { id: 2 }];
    const { cancelAllScheduled } = await fresh();
    await within(cancelAllScheduled());
    expect(touched).not.toContain('then');
    expect(calls).toContainEqual(['cancel', { notifications: [{ id: 1 }, { id: 2 }] }]);
  });

  it('постановка не трогает `then`', async () => {
    const { scheduleFromUpcoming } = await fresh();
    await expect(within(scheduleFromUpcoming(EVENTS, NOW))).resolves.toBe(1);
    expect(touched).not.toContain('then');
  });
});

describe('постановка уведомлений', () => {
  it('перед постановкой создаёт канал и снимает прежний план', async () => {
    pending = [{ id: 42 }];
    const { scheduleFromUpcoming } = await fresh();
    await within(scheduleFromUpcoming(EVENTS, NOW));

    const order = calls.map(([name]) => name);
    expect(order.indexOf('createChannel')).toBeLessThan(order.indexOf('schedule'));
    expect(order.indexOf('cancel')).toBeLessThan(order.indexOf('schedule'));
  });

  it('в плагин уходит канал, время события как есть и allowWhileIdle', async () => {
    const { scheduleFromUpcoming } = await fresh();
    await within(scheduleFromUpcoming(EVENTS, NOW));

    const scheduled = calls.find(([name]) => name === 'schedule')[1].notifications;
    expect(scheduled, 'ни одного уведомления не поставлено').toHaveLength(1);
    for (const n of scheduled) {
      expect(n.channelId).toBe('aristea-events');
      expect(n.schedule.allowWhileIdle).toBe(true);
      expect(n.schedule.at.getTime()).toBe(Date.parse(EVENTS[0].at));
    }
  });

  it('пустой план не зовёт schedule вовсе', async () => {
    const { scheduleFromUpcoming } = await fresh();
    await expect(within(scheduleFromUpcoming([], NOW))).resolves.toBe(0);
    expect(calls.map(([name]) => name)).not.toContain('schedule');
  });
});
