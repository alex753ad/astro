/**
 * supportContext.js — что уходит вместе с обращением в поддержку и в каком
 * виде это видит человек перед отправкой.
 *
 * Уходят: версия приложения, модель телефона (из user-agent WebView — без
 * плагина, решение владельца 27.09.2026), номер аккаунта и — если обращение
 * открыто с экрана ошибки — экран и текст ошибки. Email и номер аккаунта сервер
 * берёт из токена сам; email человеку показывается открыто («Ответим на почту
 * …»), потому что ответ приходит именно туда.
 *
 * ⚠️ Текст ошибки чистится `scrubErrorText` ДО показа и отправки: в текстах
 * сервера бывают email, даты, время и место рождения (место — в кавычках:
 * «Не нашли „Москва“»). Email режется тем же выражением, что в Sentry
 * (`lib/sentryScrub.js`), остальное — здесь. Показываем ровно то, что уйдёт.
 */

import { maskEmails } from '../../lib/sentryScrub';

/* global __APP_RELEASE__ */
// Определена только в сборке приложения (vite.config.mobile.js); в тестах и
// веб-сборке её нет.
const RELEASE = typeof __APP_RELEASE__ !== 'undefined' ? __APP_RELEASE__ : '';

/** «aristea-mobile@0.1.0+abc1234» → «0.1.0 (abc1234)». */
export function appVersionLabel(release = RELEASE) {
  const m = /@([^+]+)(?:\+(.+))?$/.exec(release || '');
  if (!m) return 'dev';
  return m[2] ? `${m[1]} (${m[2]})` : m[1];
}

/**
 * «aristea-mobile@0.1.0+abc1234» → «0.1.0» — для экрана «Настройки».
 * Хеш человеку ничего не говорит; он нужен только поддержке и уходит с
 * обращением через appVersionLabel (решение владельца 27.09.2026).
 */
export function appVersionShort(release = RELEASE) {
  const m = /@([^+]+)/.exec(release || '');
  return m ? m[1] : 'dev';
}

/**
 * Модель из user-agent Android WebView: «…(Linux; Android 14; SM-A515F Build/…)».
 * ⚠️ Урезанный UA (Chrome UA reduction) вместо модели пишет «K» — тогда
 * отдаём только версию Android, а не выдуманную модель.
 */
export function deviceLabel(ua = typeof navigator !== 'undefined' ? navigator.userAgent : '') {
  const m = /Android ([\d.]+);\s*([^;)]+)/.exec(ua || '');
  if (!m) return /iPhone|iPad/.test(ua || '') ? 'iOS' : 'неизвестно';
  const model = m[2].replace(/\s*Build\/.*$/, '').replace(/\s*wv$/, '').trim();
  return model && model !== 'K' ? `${model}, Android ${m[1]}` : `Android ${m[1]}`;
}

const QUOTED = /«[^»]*»|„[^“”]*[“”]|"[^"]*"/g;
const DATE = /\b\d{1,4}[./-]\d{1,2}[./-]\d{1,4}\b/g;
const DAY_MONTH = /\b\d{1,2}\s+(?:января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)/gi;
const YEAR = /\b(?:1[89]|20)\d{2}\b/g;
const TIME = /\b\d{1,2}:\d{2}(?::\d{2})?\b/g;
const COORD = /-?\d{1,3}[.,]\d{3,}/g;
const MAX_ERROR = 300;

/** Текст ошибки без email, дат, времени, координат и всего в кавычках. */
export function scrubErrorText(text) {
  if (!text) return '';
  return maskEmails(String(text))
    .replace(QUOTED, '[…]')
    .replace(DATE, '[дата]')
    .replace(DAY_MONTH, '[дата]')
    .replace(YEAR, '[год]')
    .replace(TIME, '[время]')
    .replace(COORD, '[число]')
    .slice(0, MAX_ERROR);
}
