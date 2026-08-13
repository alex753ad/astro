/**
 * Реферальный код (?ref=<code>) из адресной строки — сохраняется в
 * localStorage на 90 дней при первом заходе по ссылке, переживает переходы
 * внутри сайта (SPA-навигация не теряет localStorage).
 *
 * Один раз использованный на регистрации, дальше не нужен — сервер
 * привязывает referred_by только в момент создания аккаунта
 * (backend/auth/router.py: _create_user / google_oauth), задним числом
 * восстановить нельзя. Уже залогиненный пользователь, зашедший по чужой
 * ссылке, ничего не перезаписывает: привязка для его аккаунта либо уже
 * случилась, либо не случится никогда.
 */

const KEY = "astro_ref_code";
const TTL_MS = 90 * 24 * 60 * 60 * 1000;
const ACCESS_TOKEN_KEY = "astro_access_token";

export function captureRefCode(search) {
  const ref = new URLSearchParams(search).get("ref");
  if (!ref) return;
  if (localStorage.getItem(ACCESS_TOKEN_KEY)) return;
  localStorage.setItem(KEY, JSON.stringify({ code: ref, expiresAt: Date.now() + TTL_MS }));
}

export function getRefCode() {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return null;
    const { code, expiresAt } = JSON.parse(raw);
    if (!code || Date.now() > expiresAt) {
      localStorage.removeItem(KEY);
      return null;
    }
    return code;
  } catch {
    return null;
  }
}
