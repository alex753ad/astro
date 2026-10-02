/**
 * widgetSync.js — виджет «День» на главном экране Android (флаг widget).
 *
 * Виджет сам в сеть не ходит (почему — backend/widget.py): приложение кладёт
 * ему запас на 14 дней из /api/v1/widget через свой плагин
 * (frontend/plugins/widget). Здесь — когда класть и когда снимать.
 *
 *   · флаг включён, вошли — компонент включён, запас обновляется не чаще
 *     REFRESH_MS (и сразу, если сменились сутки);
 *   · флаг включён, не вошли — компонент включён, «Войди, чтобы видеть свой
 *     день»;
 *   · флаг выключен — запас стёрт, компонент выключен: виджет пропадает из
 *     списка, лаунчер снимает его с экрана.
 *
 * ⚠️ Решение — только по ОТВЕТУ /flags (onFlagsLoaded), не по useFlag:
 * до ответа и без сети useFlag отдаёт false, и каждый запуск без сети снимал
 * бы виджет с экрана.
 *
 * ⚠️ Объект плагина не возвращается из async-функции и не await-ится
 * (frontend/src/mobile/CLAUDE.md): под await — только промисы его методов.
 */
import { useEffect, useRef } from 'react';
import { registerPlugin } from '@capacitor/core';
import { API_BASE } from '../../config';
import { authFetch } from '../../api/client';
import { IS_MOBILE } from '../../api/authTransport';
import { onFlagsLoaded, useFlag } from '../../lib/flags';

export const WIDGET_FLAG = 'widget';
export const REFRESH_MS = 3 * 60 * 60 * 1000;

const native = { plugin: IS_MOBILE ? registerPlugin('AristeaWidget') : null };

let last = { at: 0, date: '', authed: null };
let pending = null;
let running = null;
// Для строки диагностики (widgetDiagLine): что пришло с сервера и чем
// кончился последний шаг. Ошибки по-прежнему не роняют приложение, но
// больше не пропадают молча.
let diag = { flag: null, flagAt: 0, step: 'ещё не запускался', stepAt: 0 };

function localDate(now) {
  const p = (n) => String(n).padStart(2, '0');
  return `${now.getFullYear()}-${p(now.getMonth() + 1)}-${p(now.getDate())}`;
}

/**
 * Применить ответ /flags. Вызовы не теряются: идущий доводится до конца,
 * затем применяется ПОСЛЕДНИЙ пришедший.
 *
 * ⚠️ До 02.10.2026 здесь был флаг «занято», и вызов во время идущего просто
 * отбрасывался: если ответы /flags шли подряд и первый был «выкл» (флаг
 * только что включили, а кэш сервера держит старое до 30 с), правильное
 * «вкл» пропадало до следующего возврата в приложение. Была ли это причина
 * «виджета нет в списке» на Samsung 02.10.2026 — не доказано; для этого
 * строка диагностики (widgetDiagLine).
 */
export function applyWidget(on, authed, opts = {}) {
  pending = [on, authed, opts];
  if (!running) {
    running = (async () => {
      while (pending) {
        const next = pending;
        pending = null;
        await applyOnce(...next);
      }
    })().finally(() => { running = null; });
  }
  return running;
}

async function applyOnce(on, authed, { plugin = native.plugin, fetcher = authFetch, now = new Date() }) {
  if (!plugin) return;
  diag = { ...diag, flag: on, flagAt: +now };
  const step = (text) => { diag = { ...diag, step: text, stepAt: Date.now() }; };
  try {
    step('включаю компонент');
    await plugin.setEnabled({ enabled: on });
    if (!on) {
      last = { at: 0, date: '', authed: null };
      await plugin.save({ data: '' });
      step('выключен флагом');
      return;
    }
    if (!authed) {
      if (last.authed !== false) await plugin.save({ data: JSON.stringify({ signedOut: true }) });
      last = { at: 0, date: '', authed: false };
      step('без входа');
      return;
    }
    const today = localDate(now);
    if (last.authed && last.date === today && now - last.at < REFRESH_MS) {
      step('запас свежий');
      return;
    }
    step('запрос /widget');
    const r = await fetcher(`${API_BASE}/widget`);
    if (!r.ok) {
      step(`/widget ответил ${r.status}`);
      return;
    }
    const { days } = await r.json();
    await plugin.save({ data: JSON.stringify({ days }) });
    last = { at: +now, date: today, authed: true };
    step(`запас ${days.length} дн.`);
  } catch (e) {
    // нет сети или плагина — виджет живёт на прежнем запасе
    step(`ошибка на шаге «${diag.step}»: ${e?.message || e}`);
  }
}

const hm = (t) => (t ? new Date(t).toTimeString().slice(0, 5) : '—');
const COMPONENT = { 0: 'выкл (манифест)', 1: 'вкл', 2: 'выкл', 3: 'выкл пользователем' };

/**
 * «Виджет: флаг вкл 12:01 · компонент вкл · в списке да · на экране 0 ·
 * запас 14 дн., сегодня есть · закрепление да · шаг: запас 14 дн. 12:01».
 * Нативная часть не ответила — так и пишется: это и есть диагноз.
 */
export async function widgetDiagLine(plugin = native.plugin) {
  const flag = diag.flag === null ? 'нет ответа /flags' : `флаг ${diag.flag ? 'вкл' : 'выкл'} ${hm(diag.flagAt)}`;
  let native_ = 'плагин недоступен';
  if (plugin) {
    try {
      const s = await plugin.status();
      native_ = [
        `компонент ${COMPONENT[s.component] ?? s.component}`,
        `в списке ${s.listed ? 'да' : 'нет'}`,
        `на экране ${s.placed}`,
        `запас ${s.days} дн., сегодня ${s.today ? 'есть' : 'нет'}`,
        `закрепление ${s.pin ? 'да' : 'нет'}`,
      ].join(' · ');
    } catch (e) {
      native_ = `status: ${e?.message || e}`;
    }
  }
  return `Виджет: ${flag} · ${native_} · шаг: ${diag.step} ${hm(diag.stepAt)}`;
}

/**
 * Выход из аккаунта — чужой день не должен остаться на главном экране общего
 * телефона до следующего ответа /flags. Компонент не трогаем: это решает флаг.
 */
export function signOutWidget(plugin = native.plugin) {
  if (!plugin) return;
  last = { at: 0, date: '', authed: false };
  plugin.save({ data: JSON.stringify({ signedOut: true }) }).catch(() => {});
}

/** В корне приложения (MobileApp.jsx): и для вошедшего, и для гостя. */
export function useWidgetSync(isAuthenticated) {
  useFlag(WIDGET_FLAG); // держит перезапрос /flags при возврате в приложение
  const authed = useRef(isAuthenticated);
  authed.current = isAuthenticated;
  useEffect(() => onFlagsLoaded((flags) => applyWidget(flags.has(WIDGET_FLAG), authed.current)), []);
  useEffect(() => { if (!isAuthenticated) signOutWidget(); }, [isAuthenticated]);
}

export function _resetForTests() {
  last = { at: 0, date: '', authed: null };
  pending = null;
  running = null;
  diag = { flag: null, flagAt: 0, step: 'ещё не запускался', stepAt: 0 };
}
