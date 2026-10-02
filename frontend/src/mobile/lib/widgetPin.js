/**
 * widgetPin.js — предложить поставить виджет «День» (флаг widget).
 *
 * Два места, одно правило (решения владельца 02.10.2026):
 *   · день 3 первой недели — FirstWeekCard, кнопка «Добавить виджет»
 *     (docs/first_week_widget_day.md);
 *   · кому первая неделя прошла — WidgetPinCard в ленте с 3-го дня, в который
 *     открывали приложение (docs/widget_pin_card_plan.md).
 * Кнопка — системный запрос закрепления (WidgetPlugin.requestPin): окно
 * лаунчера, одно нажатие — виджет на экране. Добавили ли, лаунчер не
 * сообщает — смотрим на status().placed при возврате (checkPlaced).
 *
 * Как не надоедать (карточка в ленте): «Не сейчас» — на 14 дней; нажали
 * «Добавить», но виджета нет — то же самое; после второго раза — никогда.
 *
 * Состояние — на устройстве (localStorage): это про этот телефон и его
 * главный экран, а не про аккаунт.
 */
import { API_BASE } from '../../config';
import { authFetch } from '../../api/client';
import { markSeen } from './firstWeek';

const KEY = 'aristea_widget_pin';
export const MIN_OPEN_DAYS = 3;
export const SNOOZE_DAYS = 14;
export const MAX_DISMISSALS = 2;

const EMPTY = { lastDay: '', openDays: 0, dismissals: 0, until: '', pending: '', added: false, shown: {} };

export function localDate(now = new Date()) {
  const p = (n) => String(n).padStart(2, '0');
  return `${now.getFullYear()}-${p(now.getMonth() + 1)}-${p(now.getDate())}`;
}

function addDays(iso, n) {
  const [y, m, d] = iso.split('-').map(Number);
  return localDate(new Date(y, m - 1, d + n));
}

export function readState() {
  try { return { ...EMPTY, ...JSON.parse(localStorage.getItem(KEY) || '{}') }; } catch { return { ...EMPTY }; }
}

function writeState(st) {
  try { localStorage.setItem(KEY, JSON.stringify(st)); } catch { /* до перезапуска */ }
}

/** Журнал для еженедельной сводки (075). Best-effort: потеря строки не важна. */
function logEvent(kind, source) {
  authFetch(`${API_BASE}/widget/event`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ kind, source }),
  }).catch(() => {});
}

/** Новый день, в который открыли приложение (счётчик «с 3-го дня»). */
export function countOpenDay(today = localDate()) {
  const st = readState();
  if (st.lastDay === today) return st.openDays;
  writeState({ ...st, lastDay: today, openDays: st.openDays + 1 });
  return st.openDays + 1;
}

/** Показ предложения — в сводку раз в местные сутки на источник. */
export function logShown(source, today = localDate()) {
  const st = readState();
  if (st.shown[source] === today) return;
  writeState({ ...st, shown: { ...st.shown, [source]: today } });
  logEvent('shown', source);
}

/** Карточка в ленте: можно ли показывать (без сети и плагина — решает вызывающий). */
export function cardAllowed(st, today, { flag, firstWeek, pin, placed, weekAhead }) {
  return flag === true && firstWeek === false && pin === true && placed === 0 && !weekAhead
    && st.openDays >= MIN_OPEN_DAYS && st.dismissals < MAX_DISMISSALS
    && (!st.until || today >= st.until);
}

export function dismiss(today = localDate()) {
  const st = readState();
  writeState({ ...st, dismissals: st.dismissals + 1, until: addDays(today, SNOOZE_DAYS), pending: '' });
}

/**
 * Системный запрос. ⚠️ plugin передаётся обёрткой { plugin }: объект
 * плагина — thenable Proxy, его нельзя возвращать и await-ить
 * (frontend/src/mobile/CLAUDE.md).
 */
export async function pin(source, { plugin }) {
  if (!plugin) return false;
  writeState({ ...readState(), pending: source });
  try {
    const { shown } = await plugin.requestPin();
    return shown;
  } catch {
    return false;
  }
}

/**
 * При возврате в приложение (и на старте), флаг widget включён и вошли.
 * Виджет на экране — пункт первой недели закрыт, «добавление» — в сводку
 * один раз на устройство. Лаунчер не умеет закреплять — пункт первой недели
 * закрыт: кнопка ничего бы не сделала. Нажали «Добавить» в карточке ленты,
 * а виджета нет — как «Не сейчас».
 */
export async function checkPlaced({ plugin }, today = localDate()) {
  if (!plugin) return null;
  let s;
  try { s = await plugin.status(); } catch { return null; }
  const st = readState();
  if (s.placed > 0) {
    if (!st.added) logEvent('added', st.pending || 'manual');
    writeState({ ...st, added: true, pending: '' });
    markSeen('widget');
  } else {
    if (!s.pin) markSeen('widget');
    if (st.pending === 'card') dismiss(today);
    else if (st.pending) writeState({ ...st, pending: '' });
  }
  return s;
}
