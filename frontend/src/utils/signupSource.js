/**
 * Источник регистрации — utm-метки первого захода на сайт (074,
 * users.signup_source). Устроено как refCode.js рядом: localStorage на 90
 * дней, уже вошедший ничего не перезаписывает.
 *
 * Первый заход, а не последний: человек, пришедший со сторис
 * (aristeatime.ru/d → /?utm_source=story&utm_medium=share&utm_campaign=day_card,
 * редирект в nginx astreatime.conf) и вернувшийся потом из поиска, —
 * всё равно «со сторис». Формат — «source/medium/campaign», нижний регистр;
 * сервер всё, что не [a-z0-9_./-]{1,64}, превращает в None
 * (schemas.SendEmailOTPRequest), регистрацию это не ломает.
 */

const KEY = 'astro_signup_source';
const TTL_MS = 90 * 24 * 60 * 60 * 1000;
const ACCESS_TOKEN_KEY = 'astro_access_token';

export function sourceFromSearch(search) {
  const q = new URLSearchParams(search);
  const src = q.get('utm_source');
  if (!src) return null;
  return [src, q.get('utm_medium') || '', q.get('utm_campaign') || '']
    .join('/').toLowerCase().slice(0, 64);
}

export function captureSignupSource(search) {
  const value = sourceFromSearch(search);
  if (!value) return;
  try {
    if (localStorage.getItem(ACCESS_TOKEN_KEY) || getSignupSource()) return;
    localStorage.setItem(KEY, JSON.stringify({ value, expiresAt: Date.now() + TTL_MS }));
  } catch { /* хранилище недоступно — источник просто не запишется */ }
}

export function getSignupSource() {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return null;
    const { value, expiresAt } = JSON.parse(raw);
    if (!value || Date.now() > expiresAt) {
      localStorage.removeItem(KEY);
      return null;
    }
    return value;
  } catch {
    return null;
  }
}
