/**
 * MoreNotificationsDebug.test.js — ВРЕМЕННЫЙ, снимается вместе с кнопкой.
 *
 * Проверяет ровно одно: собственная обёртка панели вокруг объекта плагина не
 * пропускает его под `await`. Обёртка здесь своя (чтобы удаление отладки не
 * трогало продуктовый файл), а значит и замок на неё нужен свой — правило
 * принадлежит `registerPlugin`, а не конкретному плагину: get-ловушка Proxy
 * отдаёт вызов моста для любого имени, включая `then`, и возврат такого объекта
 * из async-функции даёт не отказ, а вечное зависание мимо catch и finally
 * (CLAUDE.md, docs/HISTORY-mobile.md — там это стоило четырёх дней).
 *
 * ⚠️ Почему нельзя было просто «не забыть». Панель зовёт `getPending` при
 * каждом открытии экрана. Забытая обёртка повесила бы не отладку, а весь экран
 * «Уведомления» — молча, без единой ошибки в консоли, и выглядело бы это как
 * вечный скелет загрузки.
 *
 * Границы окна и запас здесь НЕ проверяются: они переехали в продуктовый
 * `localNotificationPlan.js` и закрыты `localNotificationPlan.test.js`. Копии
 * серверного правила в отладочном файле больше нет.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const touched = [];

/** Тот же Proxy, что делает registerPlugin: `then` — НЕ исключение. */
const pluginProxy = new Proxy({}, {
  get(_, prop) {
    touched.push(String(prop));
    if (prop === 'then') {
      return () => Promise.reject(
        new Error('"LocalNotifications.then()" is not implemented on android'),
      );
    }
    return async () => ({ notifications: [] });
  },
});

vi.mock('@capacitor/local-notifications', () => ({ LocalNotifications: pluginProxy }));

/** Зависание по таймауту читается как сломанный тест — гонка даёт внятное «ПОВИСЛО». */
function within(promise, ms = 200) {
  return Promise.race([
    promise,
    new Promise((resolve) => setTimeout(() => resolve('ПОВИСЛО'), ms)),
  ]);
}

beforeEach(() => {
  touched.length = 0;
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('обёртка отладочной панели вокруг плагина', () => {
  it('возвращает обёртку, а не сам объект, и не трогает `then`', async () => {
    const { notifications } = await import('./MoreNotificationsDebug');

    const api = await within(notifications());
    expect(api, 'вызов обёртки повис — объект плагина ушёл под await').not.toBe('ПОВИСЛО');
    expect(touched).not.toContain('then');
    expect(typeof api.plugin).toBe('object');
  });

  it('через обёртку getPending вызывается и отвечает', async () => {
    const { notifications } = await import('./MoreNotificationsDebug');

    const api = await notifications();
    await expect(within(api.plugin.getPending())).resolves.toEqual({ notifications: [] });
    expect(touched).not.toContain('then');
  });
});
