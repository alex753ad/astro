/**
 * pushNudge.js — кого и чем звать включить уведомления (решение владельца
 * 30.09.2026): экран «Присылать прогноз каждое утро?» после первого
 * показанного прогноза, а после «Не сейчас» или отказа — через 3 дня карточка
 * в ленте. Отбор — чистой функцией `decideNudge` (тест рядом), остальное —
 * хранение состояния на устройстве.
 *
 * Состояния системного разрешения (localNotifications.permissionState, общие
 * для обоих плагинов — Capacitor хранит их по имени разрешения Android):
 *   • 'prompt' — ещё не спрашивали;
 *   • 'prompt-with-rationale' — один отказ, система спросит снова;
 *   • 'denied' — второй отказ на Android 13+ (диалога больше не будет) или
 *     уведомления выключены в системе на Android до 13, где разрешения нет;
 *   • 'granted' — на Android до 13 так у всех по умолчанию.
 */

export const NUDGE_NONE = 'none';
/** Разрешение уже есть — канал включить без вопросов (Android до 13). */
export const NUDGE_SILENT = 'silent';
export const NUDGE_SCREEN = 'screen';
/** Молча запустить трёхдневный отсчёт до карточки (экран не показываем). */
export const NUDGE_WAIT = 'wait';
export const NUDGE_CARD = 'card';
/** Карточка с «Открыть настройки»: системный диалог больше не покажется. */
export const NUDGE_CARD_SETTINGS = 'card-settings';

export const CARD_DELAY_MS = 3 * 24 * 60 * 60 * 1000;

/**
 * @param {object} s
 * @param {boolean} s.registered   не гость (гостю не показываем ничего)
 * @param {boolean} s.forecastSeen прогноз хоть раз показан на этом устройстве
 * @param {string|null} s.choice   тумблер «Уведомления на этом устройстве»:
 *                                 null — не трогали, '1' / '0' — вкл / выкл
 * @param {string} s.permission    состояние системного разрешения
 * @param {number|null} s.askedAt  когда начался отсчёт до карточки
 * @param {boolean} s.cardClosed   карточку закрыли крестиком
 * @param {number} s.now
 */
export function decideNudge(s) {
  if (!s.registered || !s.forecastSeen) return NUDGE_NONE;
  // ⚠️ '0' — человек САМ выключил тумблер в «Ещё»: не уговариваем. Поэтому
  // «Не сейчас» на экране тумблер не трогает, иначе карточка не пришла бы.
  if (s.choice !== null) return NUDGE_NONE;
  if (s.permission === 'unavailable') return NUDGE_NONE;
  // Разрешение есть, а канал не включён: Android до 13 или разрешили в
  // настройках после карточки. Без включения устройство не зарегистрируется
  // и push не придут, хотя на сервере все виды включены.
  if (s.permission === 'granted') return NUDGE_SILENT;
  if (s.cardClosed) return NUDGE_NONE;
  if (s.askedAt == null) return s.permission === 'prompt' ? NUDGE_SCREEN : NUDGE_WAIT;
  if (s.now - s.askedAt < CARD_DELAY_MS) return NUDGE_NONE;
  return s.permission === 'denied' ? NUDGE_CARD_SETTINGS : NUDGE_CARD;
}

const KEY = 'aristea_push_nudge';

/** { forecastSeen, askedAt, cardClosed } — одним ключом, чтобы не расползалось. */
export function readNudge() {
  try {
    return { forecastSeen: false, askedAt: null, cardClosed: false, ...JSON.parse(localStorage.getItem(KEY) || '{}') };
  } catch {
    return { forecastSeen: false, askedAt: null, cardClosed: false };
  }
}

export function writeNudge(patch) {
  try {
    localStorage.setItem(KEY, JSON.stringify({ ...readNudge(), ...patch }));
  } catch {
    /* приватный режим webview — спросим ещё раз, не страшно */
  }
}

export function markForecastSeen() {
  if (!readNudge().forecastSeen) writeNudge({ forecastSeen: true });
}
