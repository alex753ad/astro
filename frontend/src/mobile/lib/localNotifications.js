/**
 * localNotifications.js — единственное место, где приложение разговаривает с
 * `@capacitor/local-notifications`.
 *
 * Расчёт того, ЧТО показывать, сюда не попадает вовсе — он в
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
 * источником правила, и при этом неработоспособным: версию Android из webview
 * не узнать без ещё одного плагина.
 *
 * ⚠️ Практическое следствие для экрана: на Android < 33 отказ означает, что
 * человек выключил уведомления приложению в настройках системы, и повторный
 * `requestPermissions` диалога НЕ покажет — вернёт то же самое. Поэтому
 * интерфейс обязан на отказ говорить про настройки системы, а не предлагать
 * нажать ещё раз.
 */

import { IS_MOBILE } from '../../api/authTransport';
import { CHANNEL_ID, buildPlan } from './localNotificationPlan';

/** Имя канала видно человеку в настройках уведомлений Android. */
const CHANNEL_NAME = 'События карты';

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
      description: 'Транзиты, планер и фазы Луны по вашей карте',
      importance: 3,
      visibility: 1,
    });
  } catch (err) {
    failed('создание канала', err);
  }
}

/** Снять все запланированные — при выключении тумблера и перед пересборкой плана. */
export async function cancelAllScheduled() {
  try {
    const api = await notifications();
    if (!api) return;
    const pending = await api.plugin.getPending();
    const ids = (pending?.notifications || []).map((n) => ({ id: n.id }));
    if (ids.length) await api.plugin.cancel({ notifications: ids });
  } catch (err) {
    failed('отмена', err);
  }
}

/**
 * Поставить план из выдачи `GET /api/v1/push/upcoming`.
 *
 * Сначала снимаем всё поставленное, потом ставим заново целиком. Дешевле и
 * честнее разностной синхронизации: событие могло исчезнуть из выдачи (транзит
 * пересчитан, настройки изменились), и разбирать, что именно исчезло, значит
 * держать на клиенте свою модель серверного состояния. Id при этом стабильны
 * (хэш от `key`), так что повторная постановка того же события — замена, а не
 * дубль, даже если отмена почему-то не прошла.
 *
 * ⚠️ `allowWhileIdle: true` не украшение. Точные будильники с Android 12
 * требуют отдельного разрешения, которого у нас нет и которое мы намеренно не
 * просим — плагин это учитывает и сам сваливается на неточный
 * (`setExactIfPossible`, LocalNotificationManager.java). Без allowWhileIdle
 * неточный будильник в режиме Doze откладывается до выхода из него, то есть
 * утреннее уведомление может приехать к обеду; с ним — в ближайшее окно
 * обслуживания. Минуты неточности здесь допустимы, часы — нет.
 *
 * Возвращает число ПОСТАВЛЕННЫХ уведомлений (а не событий): день с тремя
 * событиями — это одно уведомление.
 */
export async function scheduleFromUpcoming(events, nowMs = Date.now()) {
  const plan = buildPlan(events, nowMs);
  try {
    const api = await notifications();
    if (!api) return 0;

    await ensureChannel();
    await cancelAllScheduled();
    if (!plan.length) return 0;

    await api.plugin.schedule({
      notifications: plan.map((item) => ({
        id: item.id,
        title: item.title,
        body: item.body,
        channelId: CHANNEL_ID,
        // Время показа — поле `at` как есть. Тихие часы (push_quiet_from)
        // посчитал сервер; второй копии этого правила на клиенте нет.
        schedule: { at: new Date(item.at), allowWhileIdle: true },
        // Ключи доезжают до обработчика тапа, если он когда-нибудь появится:
        // по ним видно, о каком событии уведомление, без разбора текста.
        extra: { keys: item.keys, url: item.url },
      })),
    });
    return plan.length;
  } catch (err) {
    failed('постановка', err);
    return 0;
  }
}
