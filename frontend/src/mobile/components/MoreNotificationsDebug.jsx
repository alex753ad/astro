/**
 * MoreNotificationsDebug.jsx — ВРЕМЕННАЯ ОТЛАДОЧНАЯ ПАНЕЛЬ. НЕ ЧАСТЬ ПРОДУКТА.
 *
 * ⚠️ Живёт только в ветке `local-notifications` и снимается перед вливанием в
 * `main` ОДНИМ обратным коммитом. Поэтому всё, что нужно панели, лежит здесь:
 * в продуктовых файлах от неё ровно две строки — импорт и рендер в
 * `MoreNotificationsView.jsx`.
 *
 * Панель разрезает цепочку локальных уведомлений на звенья, потому что снаружи
 * все её отказы выглядят одинаково — в шторке пусто:
 *
 *   разрешение → выдача сервера → построение → БУДИЛЬНИК → показ системой
 *
 * Две кнопки отличаются ровно одним звеном, и в этом весь смысл пары:
 *
 * * **«Проверить сейчас»** — полный боевой путь, через AlarmManager
 *   (`schedulePlan`, поле `schedule` заполнено).
 * * **«Показать немедленно»** — тот же плагин, тот же канал, тот же текст, но
 *   БЕЗ поля `schedule`. Плагин в этом случае зовёт
 *   `notificationManager.notify()` синхронно
 *   (`LocalNotificationManager.buildNotification`, ветка `else` от
 *   `isScheduled()`) — то есть будильник не участвует вовсе.
 *
 * ⚠️ Читать результат надо ПАРОЙ, поодиночке они почти ничего не значат:
 *   • немедленное пришло, отложенное нет → работает всё, кроме ДОСТАВКИ
 *     будильника. Причину искать в телефоне (автозапуск на прошивках вроде
 *     MIUI/EMUI — это отдельная настройка, не «оптимизация батареи»;
 *     standby-корзина), а не в коде;
 *   • не пришло ни одно → дело не в будильниках, смотреть показ на этом
 *     устройстве (канал, разрешение, режимы «не беспокоить»);
 *   • пришли оба → цепочка целиком рабочая.
 *
 * ⚠️ КНОПКА НЕ ОБЕЩАЕТ «ЧЕРЕЗ ДВЕ МИНУТЫ». Точный будильник мы намеренно не
 * запрашиваем, плагин ставит `setAndAllowWhileIdle`, а у неточного будильника
 * верхней границы задержки нет вовсе. Обещание срока выглядит как сломанная
 * цепочка и отправляет разбор по работающему коду — на этом уже упала одна
 * приёмка. Панель говорит «НЕ РАНЬШЕ», а не «в».
 *
 * ⚠️ Проверочные уведомления НЕ входят в план: они ставятся мимо
 * `scheduleFromUpcoming`, а пересборка снимает только свои id. Поэтому возврат
 * в приложение их не сносит — и поэтому же счётчик ниже разделён на «план» и
 * «прочее».
 */

import React, { useCallback, useEffect, useState } from 'react';
import {
  CHANNEL_ID,
  QUIET_MARGIN_MINUTES,
  allowedAt,
  buildPlan,
  notificationId,
} from '../lib/localNotificationPlan';
import { ensureChannel, permissionState, schedulePlan } from '../lib/localNotifications';
import { fetchPushSettings, fetchUpcomingNotifications } from '../lib/moreApi';
import { windowFrom } from '../lib/localNotificationsSync';

/**
 * Насколько вперёд просим показать отложенное проверочное.
 *
 * Это НИЖНЯЯ граница ожидания, а не срок: раньше неточный будильник не
 * сработает никогда, позже — запросто. Пять минут, а не две: опыт состоит в
 * том, чтобы успеть свернуть приложение выбранным способом, заблокировать
 * экран и положить телефон, — на двух минутах это делается впопыхах, а спешка
 * в опыте становится третьей переменной.
 */
const TEST_LEAD_MS = 5 * 60 * 1000;

/**
 * Ключ списка «своих» id из `localNotifications.js`.
 *
 * Копия строки, а не импорт: константа там внутренняя, а тащить её наружу ради
 * временной панели значит оставить хвост в продуктовом файле после удаления
 * отладки. Разъехаться они могут только вместе с удалением самой панели.
 */
const OWNED_KEY = 'aristea_local_notification_ids';

/**
 * Id немедленного проверочного — ПОСТОЯННЫЙ, и это не лень.
 *
 * ⚠️ Немедленное уведомление плагин тоже кладёт в своё хранилище
 * (`LocalNotificationsPlugin.schedule` зовёт `appendNotifications` всегда), а
 * удаляет оттуда только приёмник при доставке по будильнику — которого здесь
 * нет. Значит запись остаётся в `getPending` навсегда. С постоянным id
 * повторные нажатия перезаписывают одну запись вместо того, чтобы копить их;
 * она видна в строке «прочее» и настоящим будильником не является.
 *
 * Гасить её через `cancel` нельзя: `LocalNotificationManager.cancel` первым
 * делом зовёт `dismissVisibleNotification(id)` — то есть убрал бы из шторки
 * ровно то, что мы пришли посмотреть.
 */
const IMMEDIATE_ID = notificationId('debug:immediate');

/**
 * Id отложенного проверочного — тоже СВОЙ, и это починка, а не украшение.
 *
 * ⚠️ До 13.09.2026 кнопка брала id из плана: она собирала уведомление из
 * событий ближайшей группы, а `buildPlan` считает id как хэш ключа ПЕРВОГО
 * события — то есть ровно тот же id, что у настоящего уведомления этой группы.
 * Последствие не «некрасиво», а разрушительно для проверки: при следующей
 * синхронизации (а её запускает любой возврат в приложение) пересборка ставит
 * этот id заново, но уже с БОЕВЫМ временем — завтрашним утром. Отмены при этом
 * не происходит, счётчик не меняется, в логах пусто: проверочный будильник
 * просто молча уезжает на сутки вперёд.
 *
 * То есть «уведомление не пришло» могло означать не отказ устройства, а нашу
 * же перезапись. Пока id общий, ни один опыт с фоном не доказывает ничего.
 * Собственный ключ выводит проверочное из множества плана: пересборка его не
 * отменяет (его нет в списке своих id) и не перезаписывает (id другой).
 */
const SCHEDULED_ID = notificationId('debug:scheduled');

/**
 * Обёртка вокруг объекта плагина — для `getPending` и для немедленного показа.
 *
 * ⚠️ Та же ловушка, что и везде: объект плагина Capacitor — Proxy, чья
 * get-ловушка отдаёт вызов моста для ЛЮБОГО имени, включая `then`. Вернуть его
 * из async-функции (или заawait-ить) значит пропустить через разворачивание
 * thenable и получить не отказ, а вечное зависание мимо catch и finally
 * (CLAUDE.md, docs/HISTORY-mobile.md). Возвращается обёртка `{ plugin }`.
 *
 * Отдельная копия обёртки, а не экспорт из `localNotifications.js`, —
 * сознательно: так удаление отладки не трогает продуктовый файл.
 */
export async function notifications() {
  const mod = await import('@capacitor/local-notifications');
  return { plugin: mod.LocalNotifications };
}

function readOwned() {
  try {
    const raw = JSON.parse(localStorage.getItem(OWNED_KEY) || '[]');
    return Array.isArray(raw) ? raw : [];
  } catch {
    return [];
  }
}

const box = {
  marginTop: 16,
  padding: 14,
  border: '1px dashed var(--text-secondary)',
  borderRadius: 14,
  background: 'transparent',
  display: 'flex',
  flexDirection: 'column',
  gap: 10,
};

const mono = {
  fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
  fontSize: 12,
  lineHeight: 1.6,
  color: 'var(--text-secondary)',
  whiteSpace: 'pre-wrap',
};

const btn = (busy) => ({
  padding: '11px 14px',
  borderRadius: 12,
  border: '1px dashed var(--text-secondary)',
  background: 'transparent',
  color: 'var(--text-primary)',
  fontFamily: 'var(--font-body)',
  fontSize: 14.5,
  opacity: busy ? 0.6 : 1,
});

const hhmm = (ms) =>
  new Date(ms).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });

const dayTime = (ms) =>
  new Date(ms).toLocaleString('ru-RU', {
    day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit',
  });

export default function MoreNotificationsDebug({ settings }) {
  const [diag, setDiag] = useState(null);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);

  /**
   * Состояние системы, разделённое на план и всё остальное.
   *
   * ⚠️ Раньше здесь было одно число и одно «ближайшее» по ВСЕМУ `getPending`.
   * Формально верно (getPending и есть всё хранилище плагина), но читалось как
   * загадка: «запланировано 6, ближайшее 13:56» при плане на завтрашнее утро —
   * потому что 13:56 это само проверочное, в план не входящее. Теперь множества
   * названы: план — это id, которые записала последняя пересборка, прочее —
   * всё, что в системе есть помимо него.
   */
  const refreshDiag = useCallback(async () => {
    const permission = await permissionState();
    let pending = [];
    try {
      const api = await notifications();
      pending = (await api.plugin.getPending())?.notifications || [];
    } catch (err) {
      // eslint-disable-next-line no-console
      console.warn('[debug] getPending:', err);
    }

    const owned = readOwned();
    const at = (n) => Date.parse(n?.schedule?.at);
    const times = (list) => list.map(at).filter(Number.isFinite).sort((a, b) => a - b);

    const plan = pending.filter((n) => owned.includes(n.id));
    const other = pending.filter((n) => !owned.includes(n.id));

    setDiag({
      permission,
      total: pending.length,
      plan: plan.length,
      other: other.length,
      nextPlan: times(plan)[0] ?? null,
      nextAny: times(pending)[0] ?? null,
    });
  }, []);

  useEffect(() => { refreshDiag(); }, [refreshDiag]);

  /** Ближайшая реальная группа событий + границы окна. Общее для обеих кнопок. */
  async function loadNearest() {
    const [upcoming, fresh] = await Promise.all([
      fetchUpcomingNotifications(),
      fetchPushSettings(),
    ]);
    const events = upcoming?.events || [];
    // ⚠️ Пустая выдача — это ответ, а не повод что-нибудь придумать. Подставить
    // свой текст значило бы завести второй источник формулировок, ровно то,
    // ради чего ручка `/push/upcoming` и делалась. Запрет действует и для
    // отладки: проверять надо то, что придёт человеку.
    const nearest = buildPlan(events)[0];
    return { events, nearest, win: windowFrom(upcoming, fresh || settings) };
  }

  /** Полный боевой путь: через AlarmManager. */
  async function runScheduled() {
    setBusy(true);
    setMessage('');
    try {
      const { events, nearest, win } = await loadNearest();
      if (!nearest) {
        setMessage('Событий впереди нет — проверять нечего, уведомление не поставлено.');
        return;
      }

      // Ближайший РАЗРЕШЁННЫЙ срок: «сейчас + запас на два запроса», а если
      // этот момент вне окна или в запасе у верхней границы — следующий слот,
      // присланный сервером. Своего времени кнопка не собирает, как и боевой путь.
      const candidate = new Date(Date.now() + TEST_LEAD_MS).toISOString();
      const at = allowedAt(candidate, win);
      if (at === null) {
        setMessage(
          `Разрешённого времени впереди нет: окно ${win.dailyTime}–${win.quietFrom} `
          + `(по ${win.timeZone}), запас у верхней границы ${QUIET_MARGIN_MINUTES} мин. `
          + 'Уведомление не поставлено.',
        );
        return;
      }

      const moved = at !== candidate;
      const shifted = events
        .filter((e) => nearest.keys.includes(e.key))
        .map((e) => ({ ...e, at }));

      // id подменяется на собственный: с плановым проверочное перезаписывалось
      // ближайшей же синхронизацией (см. SCHEDULED_ID). Текст, склейка и канал
      // при этом остаются теми же — подменяется только идентификатор.
      const plan = buildPlan(shifted).map((item) => ({ ...item, id: SCHEDULED_ID }));
      const n = await schedulePlan(plan);
      if (!n) {
        setMessage('Плагин ничего не поставил — смотрите консоль через chrome://inspect.');
        return;
      }

      const atMs = Date.parse(at);
      setMessage(
        `ЧЕРЕЗ БУДИЛЬНИК: поставлено НЕ РАНЬШЕ ${moved ? dayTime(atMs) : hhmm(atMs)}.\n`
        + 'Будильник неточный (точный не запрашиваем осознанно), поэтому придёт '
        + 'в этот момент или позже — сдвиг до получаса нормален, это не отказ.\n'
        + (moved
          ? `Момент «сейчас + 2 мин» попал в запас у верхней границы окна `
            + `(${QUIET_MARGIN_MINUTES} мин до ${win.quietFrom}) или вне окна — `
            + 'перенесено на следующий слот сервера.\n'
          : '')
        + 'Возврат в приложение проверочное не трогает: у него свой id, '
        + 'пересборка его не отменяет и не перезаписывает.',
      );
    } catch (err) {
      setMessage(`Не получилось: ${err?.message || err}`);
    } finally {
      setBusy(false);
      refreshDiag();
    }
  }

  /**
   * Тот же показ, но мимо будильника.
   *
   * Отличие от кнопки выше ровно одно — нет поля `schedule`, поэтому плагин
   * идёт в ветку немедленного `notificationManager.notify()`. Канал, текст и
   * сам вызов `schedule()` те же, так что разница в результате указывает
   * именно на доставку будильника, а не на что-то ещё.
   */
  async function runImmediate() {
    setBusy(true);
    setMessage('');
    try {
      const { nearest } = await loadNearest();
      if (!nearest) {
        setMessage('Событий впереди нет — проверять нечего, уведомление не показано.');
        return;
      }

      await ensureChannel();
      const api = await notifications();
      await api.plugin.schedule({
        notifications: [{
          id: IMMEDIATE_ID,
          title: nearest.title,
          body: nearest.body,
          channelId: CHANNEL_ID,
          // Поля `schedule` здесь нет НАМЕРЕННО — в этом вся проверка.
          extra: { keys: nearest.keys, url: nearest.url },
        }],
      });

      setMessage(
        'МИМО БУДИЛЬНИКА: показ запрошен прямо сейчас, без AlarmManager.\n'
        + 'Если в шторке пусто — дело не в будильниках, а в показе на этом устройстве.\n'
        + 'Если появилось, а отложенное так и не приходит — работает всё, кроме '
        + 'доставки будильника: смотреть автозапуск приложения в настройках '
        + 'прошивки (это не «оптимизация батареи») и режим энергосбережения.\n'
        + 'Эта запись останется в строке «прочее» навсегда: плагин кладёт в '
        + 'хранилище и немедленные, а чистит его только доставка по будильнику. '
        + 'Настоящим будильником она не является.',
      );
    } catch (err) {
      setMessage(`Не получилось: ${err?.message || err}`);
    } finally {
      setBusy(false);
      refreshDiag();
    }
  }

  return (
    <div style={box}>
      <div style={{ ...mono, color: 'var(--text-primary)', letterSpacing: 0.5 }}>
        ОТЛАДКА · снимается перед вливанием в main
      </div>

      <button type="button" onClick={runScheduled} disabled={busy} style={btn(busy)}>
        {busy ? 'Проверяю…' : 'Проверить сейчас (через будильник)'}
      </button>

      <button type="button" onClick={runImmediate} disabled={busy} style={btn(busy)}>
        {busy ? 'Проверяю…' : 'Показать немедленно (мимо будильника)'}
      </button>

      <div style={mono}>
        {`разрешение: ${diag?.permission ?? '…'}\n`}
        {`запланировано: ${diag?.total ?? '…'} — план ${diag?.plan ?? '…'} + прочее ${diag?.other ?? '…'}\n`}
        {`ближайшее в плане: ${diag?.nextPlan ? dayTime(diag.nextPlan) : '—'}\n`}
        {`ближайшее вообще: ${diag?.nextAny ? dayTime(diag.nextAny) : '—'}\n`}
        {`окно: ${settings?.daily_time || '08:00'}–${settings?.quiet_from || '22:00'}, запас ${QUIET_MARGIN_MINUTES} мин`}
      </div>

      {message ? <div style={{ ...mono, color: 'var(--text-primary)' }}>{message}</div> : null}
    </div>
  );
}
