/**
 * flags.js — флаги функций для сайта и приложения (backend/flags.py, docs/flags.md).
 *
 *   const on = useFlag('test_flag');   // false, пока сервер не сказал иное
 *
 * Флаги берутся с сервера (GET /flags), а не из сборки: владелец включает
 * функцию в админке без деплоя и без нового APK.
 *
 * Перезапрос — при первом useFlag, при смене аккаунта и при возврате на
 * вкладку / в приложение (visibilitychange + focus + pageshow: одного
 * visibilitychange в WebView может не прийти, см. PushNudge.jsx), но не чаще
 * MIN_INTERVAL_MS. Вместе с кэшем сервера (30 с) включение доходит до минуты.
 *
 * ⚠️ Пока ответа нет или сеть упала — флаг выключен. Функция за флагом не
 * должна мелькнуть и пропасть; наоборот (появиться с задержкой) — можно.
 */

import { useEffect, useState } from 'react';
import { API_BASE } from '../config';
import { authFetch } from '../api/client';

export const MIN_INTERVAL_MS = 30_000;
const TOKEN_KEY = 'astro_access_token';

let current = new Set();
let fetchedAt = 0;
let fetchedToken = null;
let inflight = null;
const listeners = new Set();
// Подписчики на ОТВЕТ сервера, а не на значение флага: виджет (mobile/lib/
// widgetSync.js) снимает себя с экрана по «флаг выключен» — и не должен
// путать его с «флагов ещё нет» (запуск без сети).
const loadedListeners = new Set();
let loaded = false;

function readToken() {
  try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
}

export function shouldRefresh(now, lastAt, token, lastToken) {
  return token !== lastToken || now - lastAt >= MIN_INTERVAL_MS;
}

export function refreshFlags(fetcher = authFetch) {
  const token = readToken();
  if (inflight || !shouldRefresh(Date.now(), fetchedAt, token, fetchedToken)) return inflight;
  fetchedAt = Date.now();
  fetchedToken = token;
  inflight = fetcher(`${API_BASE}/flags`)
    .then((r) => (r.ok ? r.json() : null))
    .then((body) => {
      if (!Array.isArray(body?.flags)) return;
      current = new Set(body.flags);
      loaded = true;
      listeners.forEach((fn) => fn());
      loadedListeners.forEach((fn) => fn(current));
    })
    .catch(() => {})
    .finally(() => { inflight = null; });
  return inflight;
}

function onReturn() {
  if (document.visibilityState !== 'hidden') refreshFlags();
}

/** Флаг включён прямо сейчас — для кода вне React (отметки первой недели). */
export function isFlagOn(key) {
  return current.has(key);
}

export function useFlag(key) {
  const [on, setOn] = useState(() => current.has(key));
  useEffect(() => {
    const update = () => setOn(current.has(key));
    listeners.add(update);
    if (listeners.size === 1) {
      document.addEventListener('visibilitychange', onReturn);
      window.addEventListener('focus', onReturn);
      window.addEventListener('pageshow', onReturn);
    }
    update();
    refreshFlags();
    return () => {
      listeners.delete(update);
      if (listeners.size === 0) {
        document.removeEventListener('visibilitychange', onReturn);
        window.removeEventListener('focus', onReturn);
        window.removeEventListener('pageshow', onReturn);
      }
    };
  }, [key]);
  return on;
}

/**
 * fn(flags) — после каждого успешного ответа /flags; если ответ уже был,
 * fn зовётся сразу. Перезапрос сам не включает — его держит useFlag.
 */
export function onFlagsLoaded(fn) {
  loadedListeners.add(fn);
  if (loaded) fn(current);
  return () => loadedListeners.delete(fn);
}

export function _resetForTests() {
  current = new Set(); fetchedAt = 0; fetchedToken = null; inflight = null; listeners.clear();
  loadedListeners.clear(); loaded = false;
}
