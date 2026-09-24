/**
 * sentryScrub.js — фильтр событий Sentry, общий для веба (main.jsx) и
 * приложения (main.mobile.jsx). Пара на бэкенде — backend/sentry_setup.py.
 *
 * ⚠️ Персональных данных в событиях быть не должно: дат и мест рождения,
 * текстов чата, email. `sendDefaultPii: false` убирает только то, что SDK
 * собирает сам, поэтому поверх него:
 *  - тело запроса и query string — удаляются целиком;
 *  - хлебные крошки — только сетевые и переходы, у URL срезается всё после
 *    `?`. Крошки консоли и кликов выброшены: в консоль попадают данные
 *    ответов, в клик — текст нажатого элемента;
 *  - `user` не передаётся;
 *  - email в текстах ошибок заменяется на `[email]` целиком — без первой
 *    буквы и домена; на скраббер Sentry не полагаемся (настройка проекта).
 *
 * Файл намеренно не импортирует SDK: иначе при пустом VITE_SENTRY_DSN SDK
 * перестал бы вырезаться из бандла (см. assert-bundle.mjs).
 */

const KEPT_CRUMBS = new Set(['fetch', 'xhr', 'navigation']);
const EMAIL = /[\w.+-]+@[\w-]+\.[\w.-]+/g;

const stripQuery = (url) => (typeof url === 'string' ? url.split('?')[0] : url);
const maskEmails = (s) => (typeof s === 'string' ? s.replace(EMAIL, '[email]') : s);

export function scrubEvent(event) {
  delete event.user;

  if (event.request) {
    delete event.request.data;
    delete event.request.query_string;
    delete event.request.cookies;
    event.request.url = stripQuery(event.request.url);
  }

  if (Array.isArray(event.breadcrumbs)) {
    event.breadcrumbs = event.breadcrumbs
      .filter((c) => KEPT_CRUMBS.has(c.category))
      .map((c) => {
        const data = { ...(c.data || {}) };
        for (const k of ['url', 'from', 'to']) data[k] = stripQuery(data[k]);
        return { ...c, data, message: stripQuery(c.message) };
      });
  }

  event.message = maskEmails(event.message);
  for (const ex of event.exception?.values || []) ex.value = maskEmails(ex.value);

  return event;
}
