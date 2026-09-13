/**
 * localNotifications.test.js — два замка на этом файле.
 *
 * 1. **Объект плагина не попадает под await.** Дефект принадлежит не
 *    `Preferences`, а `registerPlugin`: объект ЛЮБОГО плагина — Proxy, чья
 *    get-ловушка отдаёт вызов моста для любого имени, включая `then`, то есть
 *    он thenable. `return LocalNotifications` из async-функции пропустил бы его
 *    через разворачивание thenable — получилось бы не падение, а ВЕЧНОЕ
 *    ЗАВИСАНИЕ мимо catch и мимо finally. В `Preferences` это стоило четырёх
 *    дней разбора (docs/HISTORY-mobile.md). Правило записано в CLAUDE.md, но
 *    записи мало: соблюдение проверяется здесь.
 *
 * 2. **Пересборка трогает ровно своё множество.** До 13.09.2026 она снимала
 *    всё, что вернул `getPending`, без разбора, то есть съедала любое
 *    уведомление, поставленное не ею, — и делала это при первом же возврате в
 *    приложение, то есть ровно тогда, когда человек заходит посмотреть,
 *    пришло ли. Снаружи выглядело как «уведомление не пришло».
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
const OWNED_KEY = 'aristea_local_notification_ids';

/**
 * Минимальный localStorage вместо DOM-окружения.
 *
 * Список своих id хранится в нём, но сам дефект — про промисы и про множества
 * id, а не про браузер. Поднимать ради него jsdom значило бы менять окружение
 * всего файла и замедлять прогон на порядок; заглушка на пять строк даёт ровно
 * то поведение, на которое код опирается.
 */
const memoryStorage = new Map();
globalThis.localStorage = {
  getItem: (k) => (memoryStorage.has(k) ? memoryStorage.get(k) : null),
  setItem: (k, v) => memoryStorage.set(k, String(v)),
  removeItem: (k) => memoryStorage.delete(k),
  clear: () => memoryStorage.clear(),
};

const cancelled = () =>
  calls.filter(([name]) => name === 'cancel').flatMap(([, o]) => o.notifications.map((n) => n.id));

beforeEach(() => {
  touched.length = 0;
  calls.length = 0;
  permission = 'granted';
  pending = [];
  localStorage.clear();
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
    const { cancelNotifications } = await fresh();
    await within(cancelNotifications([1, 2]));
    expect(touched).not.toContain('then');
    expect(cancelled()).toEqual([1, 2]);
  });

  it('постановка не трогает `then`', async () => {
    const { scheduleFromUpcoming } = await fresh();
    await expect(within(scheduleFromUpcoming(EVENTS, NOW))).resolves.toBe(1);
    expect(touched).not.toContain('then');
  });
});

describe('постановка уведомлений', () => {
  it('перед постановкой создаёт канал', async () => {
    const { scheduleFromUpcoming } = await fresh();
    await within(scheduleFromUpcoming(EVENTS, NOW));
    const order = calls.map(([name]) => name);
    expect(order.indexOf('createChannel')).toBeLessThan(order.indexOf('schedule'));
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

  it('schedulePlan ничего не отменяет — это не его дело', async () => {
    pending = [{ id: 777 }];
    const { schedulePlan } = await fresh();
    await within(schedulePlan([{ id: 1, keys: ['k'], at: EVENTS[0].at, title: 'т', body: 'б', url: '/' }]));
    expect(calls.map(([name]) => name)).not.toContain('cancel');
  });
});

describe('пересборка трогает ровно своё множество', () => {
  it('чужие запланированные не отменяются — их id нет в нашем списке', async () => {
    // 777 — уведомление, поставленное в обход плана: стоит в системе, но нам
    // не принадлежит. Именно такие исчезали до 13.09.2026.
    pending = [{ id: 777 }];
    localStorage.setItem(OWNED_KEY, JSON.stringify([]));

    const { scheduleFromUpcoming } = await fresh();
    await within(scheduleFromUpcoming(EVENTS, NOW));

    expect(cancelled()).not.toContain(777);
  });

  it('своё прежнее, которого нет в новом плане, снимается', async () => {
    const { scheduleFromUpcoming, ...rest } = await fresh();
    void rest;
    localStorage.setItem(OWNED_KEY, JSON.stringify([111, 222]));

    await within(scheduleFromUpcoming(EVENTS, NOW));

    const removed = cancelled();
    expect(removed, 'в выборке нет ни одного устаревшего id').toContain(111);
    expect(removed).toContain(222);
  });

  it('своё, оставшееся в плане, не снимается и не мигает', async () => {
    const { scheduleFromUpcoming } = await fresh();
    await within(scheduleFromUpcoming(EVENTS, NOW));
    const ids = JSON.parse(localStorage.getItem(OWNED_KEY));
    expect(ids).toHaveLength(1);

    calls.length = 0;
    await within(scheduleFromUpcoming(EVENTS, NOW));
    expect(cancelled(), 'уведомление из плана сняли и поставили заново').toHaveLength(0);
  });

  it('после постановки список своих id записан', async () => {
    const { scheduleFromUpcoming } = await fresh();
    await within(scheduleFromUpcoming(EVENTS, NOW));
    const ids = JSON.parse(localStorage.getItem(OWNED_KEY));
    const scheduled = calls.find(([name]) => name === 'schedule')[1].notifications;
    expect(ids).toEqual(scheduled.map((n) => n.id));
  });

  it('выключение тумблера снимает план и только его', async () => {
    pending = [{ id: 777 }];
    localStorage.setItem(OWNED_KEY, JSON.stringify([111]));

    const { cancelOwnedPlan } = await fresh();
    await within(cancelOwnedPlan());

    expect(cancelled()).toEqual([111]);
    expect(JSON.parse(localStorage.getItem(OWNED_KEY))).toEqual([]);
  });
});

describe('запас у верхней границы доезжает до плагина', () => {
  it('событие в запасе ставится на следующий слот сервера, а не на своё время', async () => {
    const slots = ['2026-09-14T08:00:00+03:00', '2026-09-15T08:00:00+03:00'];
    const late = [{ ...EVENTS[0], key: 'transit:late', at: '2026-09-14T21:50:00+03:00' }];
    const win = { dailyTime: '08:00', quietFrom: '22:00', timeZone: 'Europe/Moscow', slots };

    const { scheduleFromUpcoming } = await fresh();
    await within(scheduleFromUpcoming(late, NOW, win));

    const scheduled = calls.find(([name]) => name === 'schedule')[1].notifications;
    expect(scheduled, 'ни одного уведомления не поставлено').toHaveLength(1);
    expect(scheduled[0].schedule.at.getTime()).toBe(Date.parse(slots[1]));
  });
});
