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

/**
 * Отметка ставится, когда текст прогноза пришёл (не на «Прогноз готовится…»).
 * Событие — чтобы PushNudge проверил сразу, а не ждал следующего повода:
 * без него на Android до 13 канал не включался (приёмка APK №119, 30.09.2026).
 */
export const FORECAST_SEEN_EVENT = 'aristea:forecast-seen';

export function markForecastSeen() {
  if (readNudge().forecastSeen) return;
  writeNudge({ forecastSeen: true });
  try { window.dispatchEvent(new Event(FORECAST_SEEN_EVENT)); } catch { /* не браузер */ }
}

// ─── Диагностика: строка в «Ещё» → «Уведомления» ─────────────────────────────
// Включается нажатием на «Версия …» в «Ещё» (решение владельца 30.09.2026),
// без этого экран уведомлений не меняется. Нужна, чтобы на приёмке видеть,
// какое условие не прошло, без компьютера и chrome://inspect.

const DIAG_KEY = 'aristea_push_diag';

export function pushDiagOn() {
  try { return localStorage.getItem(DIAG_KEY) === '1'; } catch { return false; }
}

export function togglePushDiag() {
  const next = !pushDiagOn();
  try { localStorage.setItem(DIAG_KEY, next ? '1' : '0'); } catch { /* до перезапуска */ }
  return next;
}

export const NUDGE_RU = {
  [NUDGE_NONE]: 'ничего', [NUDGE_SILENT]: 'молча', [NUDGE_SCREEN]: 'экран', [NUDGE_WAIT]: 'ждать',
  [NUDGE_CARD]: 'карточка', [NUDGE_CARD_SETTINGS]: 'карточка с настройками',
};
export const ENABLE_RU = { server: 'сервер', device: 'устройство', fail: 'не вышло' };
const TRIGGER_RU = {
  mount: 'открытие ленты', forecast: 'прогноз загрузился', tab: 'возврат на ленту', resume: 'возврат в приложение',
  button: 'кнопка',
};

/** Входы и итог последней проверки — одной строкой по-русски. */
export function diagLine(st, choice, now = Date.now()) {
  const yn = (v) => (v ? 'да' : 'нет');
  const last = st.last || {};
  const t = (ms) => (ms ? new Date(ms).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : '—');
  return [
    `прогноз показан: ${yn(st.forecastSeen)}`,
    `тумблер: ${choice === '1' ? 'вкл' : choice === '0' ? 'выкл' : 'не трогали'}`,
    `разрешение: ${last.permission || '—'}`,
    `отсчёт с: ${t(st.askedAt)}${st.askedAt && now - st.askedAt < CARD_DELAY_MS ? ' (3 дня не прошли)' : ''}`,
    `карточка закрыта: ${yn(st.cardClosed)}`,
    `проверка: ${t(last.at)}, ${TRIGGER_RU[last.trigger] || '—'} → ${NUDGE_RU[last.result] || '—'}`,
    `включение: ${ENABLE_RU[last.enable] || '—'}`,
  ].join(' · ');
}
