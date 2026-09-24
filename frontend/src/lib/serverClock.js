/**
 * serverClock.js — «сейчас» по часам СЕРВЕРА, а не телефона.
 *
 * Часы телефона бывают неверны: выставлены руками, сбиты после разряда,
 * отстают на год после сброса. Приложение не имеет права от этого
 * ломаться. Сдвиг узнаём бесплатно, без отдельного запроса: у только что
 * выданного access-токена claim `iat` — момент выдачи по часам сервера.
 * `iat − Date.now()` в момент получения и есть расхождение часов (плюс
 * задержка сети — доли секунды, для дат и сроков токена это ничто).
 *
 * Кто этим пользуется и что ломалось без этого:
 *   • срок токена (lib/jwt.js, lib/refreshSchedule.js). Access живёт 15
 *     минут; если телефон спешит больше чем на ~13, каждый свежий токен
 *     кажется протухшим — `nextRefresh` отвечает «сейчас», и сессия
 *     обновляется по кругу, пока не упрётся в лимит nginx на /auth/;
 *   • «сегодня» (localToday, todayLocalISO): это момент по серверу,
 *     показанный в поясе телефона. С неверной датой на телефоне лента
 *     открывалась бы не на том дне, а карточка «Сегодня» просила бы у
 *     сервера дату, которую он не открывает (404).
 *
 * ⚠️ Отмечать можно ТОЛЬКО токен, выданный прямо сейчас (ответ входа или
 * обновления). Токен из хранилища выдан когда-то раньше — его `iat` дал бы
 * сдвиг, равный его возрасту.
 *
 * Пояс остаётся поясом телефона: сервер знает момент, но не то, где человек.
 */

const STORAGE_KEY = 'aristea_clock_skew_ms';

/** Меньше этого расхождение не учитываем: это задержка сети, а не часы. */
const NOISE_MS = 5000;

let skewMs = readStored();

function readStored() {
  try {
    const v = Number(localStorage.getItem(STORAGE_KEY));
    return Number.isFinite(v) ? v : 0;
  } catch {
    return 0;
  }
}

function tokenIssuedAt(token) {
  try {
    const iat = JSON.parse(atob(token.split('.')[1]))?.iat;
    return typeof iat === 'number' ? iat * 1000 : 0;
  } catch {
    return 0;
  }
}

/** Запомнить расхождение по только что выданному токену. */
export function noteFreshToken(token, localNow = Date.now()) {
  const issued = token ? tokenIssuedAt(token) : 0;
  if (!issued) return;
  const raw = issued - localNow;
  skewMs = Math.abs(raw) < NOISE_MS ? 0 : raw;
  try { localStorage.setItem(STORAGE_KEY, String(skewMs)); } catch { /* только память */ }
}

/** Текущий момент по серверу, миллисекунды эпохи. */
export function serverNow() {
  return Date.now() + skewMs;
}

/** Для тестов. */
export function _resetServerClock(value = 0) {
  skewMs = value;
}
