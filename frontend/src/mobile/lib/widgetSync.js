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
let busy = false;

function localDate(now) {
  const p = (n) => String(n).padStart(2, '0');
  return `${now.getFullYear()}-${p(now.getMonth() + 1)}-${p(now.getDate())}`;
}

/** Одно применение ответа /flags. Ошибки глотаются: виджет — не повод ронять приложение. */
export async function applyWidget(on, authed, { plugin = native.plugin, fetcher = authFetch, now = new Date() } = {}) {
  if (!plugin || busy) return;
  busy = true;
  try {
    await plugin.setEnabled({ enabled: on });
    if (!on) {
      last = { at: 0, date: '', authed: null };
      await plugin.save({ data: '' });
      return;
    }
    if (!authed) {
      if (last.authed !== false) await plugin.save({ data: JSON.stringify({ signedOut: true }) });
      last = { at: 0, date: '', authed: false };
      return;
    }
    const today = localDate(now);
    if (last.authed && last.date === today && now - last.at < REFRESH_MS) return;
    const r = await fetcher(`${API_BASE}/widget`);
    if (!r.ok) return;
    const { days } = await r.json();
    await plugin.save({ data: JSON.stringify({ days }) });
    last = { at: +now, date: today, authed: true };
  } catch {
    // нет сети или плагина (сборка без него) — виджет живёт на прежнем запасе
  } finally {
    busy = false;
  }
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
  busy = false;
}
