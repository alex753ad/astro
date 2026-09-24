/**
 * localNotifications.js — единственное место, где приложение разговаривает с
 * `@capacitor/local-notifications`.
 *
 * Расчёт того, ЧТО показывать и КОГДА, сюда не попадает вовсе — он в
 * `localNotificationPlan.js`, без единого обращения к Capacitor, и потому
 * проверяется обычным прогоном тестов. Здесь остаётся только «поставить
 * насчитанное», и весь этот файл на устройстве не проверяется ничем, кроме
 * приёмки.
 *
 * ⚠️ ОБЪЕКТ ПЛАГИНА НЕ ВОЗВРАЩАЕТСЯ ИЗ async-ФУНКЦИИ И НЕ AWAIT-ИТСЯ.
 * `LocalNotifications`, как и `Preferences`, — не объект, а Proxy из
 * `registerPlugin` (@capacitor/core): его get-ловушка отдаёт вызов моста для
 * ЛЮБОГО имени свойства, включая `then`, то есть Proxy является thenable.
 * `return LocalNotifications` из async-функции пропустил бы его через
 * разворачивание thenable — мост принял бы `then` за имя метода плагина, а
 * `resolve`/`reject` за его аргументы и не вызвал бы никогда. Получилось бы не
 * падение, а ВЕЧНОЕ ЗАВИСАНИЕ, мимо catch и мимо finally. Разбор целиком —
 * CLAUDE.md, раздел про Capacitor, и docs/HISTORY-mobile.md; цена ошибки там
 * измерена: четыре дня. Поэтому ниже возвращается обёртка `{ plugin }`.
 *
 * ⚠️ Ветвление по версии Android ЗДЕСЬ НЕ ПИШЕТСЯ, и это не пропуск.
 * POST_NOTIFICATIONS существует с API 33, а minSdkVersion у нас 23, значит
 * ветвление обязательно — но оно уже есть, и оно нативное:
 * `LocalNotificationsPlugin.java` в `checkPermissions`/`requestPermissions`
 * сам проверяет `Build.VERSION.SDK_INT < TIRAMISU` и на старых версиях
 * отвечает состоянием системного переключателя уведомлений
 * (`areNotificationsEnabled`) вместо рантайм-разрешения (прочитано в
 * node_modules 13.09.2026). Своя копия этой проверки в JS была бы вторым
 * источником правила, и при этом неработоспособной: версию Android из webview
 * не узнать без ещё одного плагина.
 *
 * ⚠️ Практическое следствие для экрана: на Android < 33 отказ означает, что
 * человек выключил уведомления приложению в настройках системы, и повторный
 * `requestPermissions` диалога НЕ покажет — вернёт то же самое. Поэтому
 * интерфейс обязан на отказ говорить про настройки системы, а не предлагать
 * нажать ещё раз.
 *
 * ⚠️ БУДИЛЬНИК НЕТОЧНЫЙ, И ЭТО РЕШЕНИЕ, А НЕ НЕДОДЕЛКА (владелец, 13.09.2026).
 * Ни `SCHEDULE_EXACT_ALARM`, ни `USE_EXACT_ALARM` в манифест не добавляются:
 * впереди публикация в Google Play, где такое разрешение пришлось бы
 * обосновывать, а утренней сводке точность до минуты не нужна — сдвиг на
 * 20–40 минут признан приемлемым. Плагин без этих разрешений сам уходит в
 * `setAndAllowWhileIdle` (`LocalNotificationManager.setExactIfPossible`).
 * Практическое следствие, которое стоило одной приёмки: НЕЛЬЗЯ обещать показ
 * «через N минут» — ни в интерфейсе, ни в проверочных кнопках. Можно обещать
 * только «не раньше».
 */

import { IS_MOBILE } from '../../api/authTransport';
import { CHANNEL_ID, applyQuietMargin, buildPlan } from './localNotificationPlan';

/** Имя канала видно человеку в настройках уведомлений Android. */
const CHANNEL_NAME = 'События карты';

/**
 * Id уведомлений, поставленных ПОСЛЕДНЕЙ пересборкой плана.
 *
 * ⚠️ Ради этого списка всё и заведено: пересборка обязана трогать ровно своё
 * множество. До 13.09.2026 она снимала всё, что вернул `getPending`, без
 * разбора — то есть съедала любое уведомление, поставленное не ею. Хуже того,
 * проверка «плана нет — выходим» стояла ПОСЛЕ отмены, так что временно
 * опустевшая выдача оставляла человека вообще без уведомлений. Разбор —
 * docs/HISTORY-push.md.
 *
 * Хранится в localStorage, а не в памяти: между двумя пересборками приложение
 * успевает умереть, а уведомления в системе — нет.
 */
const OWNED_KEY = 'aristea_local_notification_ids';

function readOwned() {
  try {
    const raw = JSON.parse(localStorage.getItem(OWNED_KEY) || '[]');
    return Array.isArray(raw) ? raw.filter((n) => Number.isInteger(n)) : [];
  } catch {
    return [];
  }
}

function writeOwned(ids) {
  try {
    localStorage.setItem(OWNED_KEY, JSON.stringify(ids));
  } catch {
    /* приватный режим webview — в худшем случае старый план переживёт пересборку */
  }
}

/**
 * Обёртка вокруг объекта плагина — см. предупреждение в шапке файла.
 * `null` в вебе: пакет не должен попадать в веб-бандл даже отдельным чанком,
 * поэтому импорт динамический и внутри мобильной ветки.
 */
async function notifications() {
  if (!IS_MOBILE) return null;
  const mod = await import('@capacitor/local-notifications');
  return { plugin: mod.LocalNotifications };
}

function failed(action, err) {
  // eslint-disable-next-line no-console
  console.warn(`[push] локальные уведомления (${action}):`, err);
}

/** В вебе локальных уведомлений нет — там работают веб-пуши. */
export const LOCAL_NOTIFICATIONS_SUPPORTED = IS_MOBILE;

/**
 * 'granted' | 'denied' | 'prompt' | 'unavailable'.
 *
 * 'unavailable' — веб или отказавший мост; отличается от 'denied' тем, что
 * спрашивать бессмысленно, а не «человек сказал нет».
 */
export async function permissionState() {
  try {
    const api = await notifications();
    if (!api) return 'unavailable';
    const res = await api.plugin.checkPermissions();
    return res?.display || 'prompt';
  } catch (err) {
    failed('проверка разрешения', err);
    return 'unavailable';
  }
}

/**
 * Системный диалог разрешения.
 *
 * ⚠️ Звать только из места, где человек выразил намерение (тумблер), и только
 * после экрана-предисловия. На Android отказ окончателен: обычными средствами
 * человек его не вернёт, то есть один вопрос в неудачный момент закрывает
 * канал навсегда. То же правило и по той же причине действует в вебе
 * (CLAUDE.md, «Разрешение спрашивается только при выраженном намерении»).
 */
export async function requestPermission() {
  try {
    const api = await notifications();
    if (!api) return 'unavailable';
    const res = await api.plugin.requestPermissions();
    return res?.display || 'denied';
  } catch (err) {
    failed('запрос разрешения', err);
    return 'unavailable';
  }
}

/**
 * Канал Android. Без него на Android 8+ уведомление не покажется вовсе —
 * система отбрасывает всё, что пришло в несуществующий канал.
 *
 * Вызов идемпотентен: повторное создание канала с тем же id ничего не меняет
 * (и не может изменить — после создания важность и звук канала принадлежат
 * пользователю, а не приложению).
 *
 * importance 3 (DEFAULT) — уведомление со звуком, но без всплывающей поверх
 * экрана карточки. Это утренняя сводка, а не звонок.
 */
export async function ensureChannel() {
  try {
    const api = await notifications();
    if (!api) return;
    await api.plugin.createChannel({
      id: CHANNEL_ID,
      name: CHANNEL_NAME,
      description: 'Транзиты, планер и фазы Луны по твоей карте',
      importance: 3,
      visibility: 1,
    });
  } catch (err) {
    failed('создание канала', err);
  }
}

/**
 * Поставить готовый план. НИЧЕГО не отменяет и ничего не запоминает.
 *
 * Низкий уровень: отмена прежнего плана — дело `scheduleFromUpcoming`, а
 * поставить одно уведомление, не трогая чужие, нужно и ему, и отладочной
 * панели. Разделение именно здесь: «поставить» и «прибраться за собой» —
 * разные действия, и смешанными они и дали дефект, из-за которого пересборка
 * съедала чужое.
 *
 * ⚠️ `allowWhileIdle: true` не украшение и не замена точному будильнику.
 * Точный мы намеренно не просим (см. шапку файла), поэтому плагин ставит
 * неточный; без `allowWhileIdle` неточный будильник в режиме Doze
 * откладывается до выхода из него, то есть утреннее уведомление может приехать
 * к обеду. С ним — в ближайшее окно обслуживания. Десятки минут неточности
 * здесь допустимы, часы — нет.
 */
export async function schedulePlan(plan) {
  if (!plan.length) return 0;
  try {
    const api = await notifications();
    if (!api) return 0;

    await ensureChannel();
    await api.plugin.schedule({
      notifications: plan.map((item) => ({
        id: item.id,
        title: item.title,
        body: item.body,
        channelId: CHANNEL_ID,
        // Время показа — строка `at` как есть: либо присланная сервером, либо
        // другая из присланных (запас у верхней границы, localNotificationPlan).
        // Своего времени клиент не собирает.
        schedule: { at: new Date(item.at), allowWhileIdle: true },
        // Ключи — по ним видно, о каком событии уведомление, без разбора
        // текста. target читает обработчик нажатия (notificationTap.js).
        extra: { keys: item.keys, url: item.url, target: item.target || null },
      })),
    });
    return plan.length;
  } catch (err) {
    failed('постановка', err);
    return 0;
  }
}

/** Снять перечисленные id. Пустой список — не повод ходить в мост. */
export async function cancelNotifications(ids) {
  if (!ids.length) return;
  try {
    const api = await notifications();
    if (!api) return;
    await api.plugin.cancel({ notifications: ids.map((id) => ({ id })) });
  } catch (err) {
    failed('отмена', err);
  }
}

/**
 * Снять план целиком — при выключении тумблера.
 *
 * Снимает ровно СВОИ id. Одноразовое уведомление, поставленное в обход плана
 * (`schedulePlan` напрямую), частью плана не является и здесь не трогается:
 * его поставили отдельным решением, и сносить его выключением тумблера значило
 * бы отменять чужое действие задним числом.
 */
export async function cancelOwnedPlan() {
  const owned = readOwned();
  writeOwned([]);
  await cancelNotifications(owned);
}

/**
 * Поставить план из выдачи `GET /api/v1/push/upcoming` — боевой путь целиком.
 *
 * `win` — границы окна для запаса у верхней границы:
 * `{ dailyTime, quietFrom, timeZone, slots }`, где `slots` это строки `at`,
 * присланные сервером. Без него запас не применяется: догадываться о границах
 * нельзя, а двигать событие «на всякий случай» — значит выдумывать время.
 *
 * Порядок операций и почему он такой:
 *   1. запас — ДО склейки, иначе переехавшее событие приедет отдельным
 *      уведомлением в ту же минуту вместо того, чтобы склеиться;
 *   2. отменяем только СВОЁ прежнее и только то, чего нет в новом плане, —
 *      чужое (проверочное из панели) не трогаем;
 *   3. ставим новый план и запоминаем его id.
 *
 * Id стабильны (хэш от `key`), поэтому событие, оставшееся в плане, на шаге 2
 * не отменяется вовсе, а на шаге 3 просто перезаписывается — без мигания
 * «снято/поставлено».
 *
 * Возвращает число ПОСТАВЛЕННЫХ уведомлений (а не событий): день с тремя
 * событиями — это одно уведомление.
 */
export async function scheduleFromUpcoming(events, nowMs = Date.now(), win = null) {
  const { events: adjusted } = applyQuietMargin(events, win);
  const plan = buildPlan(adjusted, nowMs);
  const ids = plan.map((item) => item.id);

  const stale = readOwned().filter((id) => !ids.includes(id));
  await cancelNotifications(stale);

  if (!plan.length) {
    writeOwned([]);
    return 0;
  }

  const n = await schedulePlan(plan);
  // Запоминаем только то, что реально встало: иначе после отказа моста мы
  // считали бы своими id, которых в системе нет, и следующая пересборка
  // отменяла бы пустоту.
  writeOwned(n ? ids : []);
  return n;
}
