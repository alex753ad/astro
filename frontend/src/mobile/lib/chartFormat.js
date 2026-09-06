/**
 * chartFormat.js — числа сервера в строки экрана (§7 спецификации).
 *
 * Сервер отдаёт градусы десятичными (`24.0699`), а прототип требует
 * «24° 04′ 12″». Ни минут, ни секунд, ни готовой строки в ответе нет
 * (CHART_API_RECON.md §5) — собираем здесь.
 *
 * Русские названия планет и знаков берутся из feedTime.js: словари уже
 * есть, и второй их копии заводить не нужно.
 */

import { PLANET_RU, SIGN_RU } from './feedTime';

/**
 * `24.0699` → `24° 04′ 12″`.
 *
 * ⚠️ Перенос при округлении обязателен: без него `23.99999` даёт
 * «23° 59′ 60″» — секунд, равных шестидесяти, не бывает. Поэтому секунды
 * округляются ПЕРВЫМИ, а перенос идёт вверх по разрядам.
 */
export function toDMS(decimalDegrees) {
  if (typeof decimalDegrees !== 'number' || Number.isNaN(decimalDegrees)) return '';
  const total = Math.abs(decimalDegrees);
  let deg = Math.floor(total);
  let min = Math.floor((total - deg) * 60);
  let sec = Math.round((((total - deg) * 60) - min) * 60);
  if (sec === 60) { sec = 0; min += 1; }
  if (min === 60) { min = 0; deg += 1; }
  const pad = (n) => String(n).padStart(2, '0');
  return `${deg}° ${pad(min)}′ ${pad(sec)}″`;
}

/**
 * Градус куспида внутри знака.
 *
 * ⚠️ У дома `degree` — АБСОЛЮТНАЯ долгота 0–360, а у планеты
 * `degree_in_sign` — уже градус внутри знака. Поля названы почти
 * одинаково, значат разное (CHART_API_RECON.md §2) — эта функция для
 * первого случая, планетам она не нужна.
 */
export function degreeInSign(absoluteLongitude) {
  return ((absoluteLongitude % 30) + 30) % 30;
}

export function planetRu(name) {
  return PLANET_RU[name] || name || '';
}

export function signRu(sign) {
  return SIGN_RU[sign] || sign || '';
}

// Названия аспектов словами — третья копия того же словаря в проекте
// (первая — TransitTimeline.jsx на вебе, вторая была в templates.json до
// её отмены). Разрешено по той же причине, что и SIGN_RU: пять слов,
// которые не меняются, дешевле вынести сюда, чем связывать мобильное
// приложение с боевым веб-компонентом ради них.
const ASPECT_RU = {
  conjunction: 'соединение',
  sextile: 'секстиль',
  square: 'квадрат',
  trine: 'трин',
  opposition: 'оппозиция',
};

export function aspectRu(type) {
  return ASPECT_RU[type] || type || '';
}

/** «I» … «XII» — номера домов принято писать римскими. */
const ROMAN = ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X', 'XI', 'XII'];

export function romanHouse(number) {
  return ROMAN[number - 1] || String(number);
}

// Месяцы в родительном — «15 июня 1990» (тот же падеж и та же причина, что
// в feedTime.js: списком, а не через Intl, потому что ICU в webview Android
// может приехать урезанным и отдать английские названия).
const MONTHS_GENITIVE = [
  'января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
  'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря',
];

/** «1990-06-15» → «15 июня 1990». Срез строки, без Date и без зон. */
export function birthDateWords(dateStr) {
  if (typeof dateStr !== 'string' || dateStr.length < 10) return '';
  const [y, m, d] = dateStr.split('-').map(Number);
  return `${d} ${MONTHS_GENITIVE[m - 1] || ''} ${y}`;
}

/**
 * «Москва, Центральный федеральный округ, Россия» → «Москва».
 *
 * Полный адрес геокодера в строку шапки не влезает и ничего не добавляет:
 * человек знает, где он родился. Берём первую часть до запятой.
 */
export function shortPlace(place) {
  return typeof place === 'string' ? place.split(',')[0].trim() : '';
}

/**
 * Пара «Северный узел ↔ Южный узел» — артефакт расчёта: узлы по
 * определению напротив друг друга, поэтому оппозиция с орбом 0.0 приходит
 * на ЛЮБОЙ карте (проверено на обеих картах служебного аккаунта). В
 * списке аспектов это шум, одинаковый у всех.
 */
export function isNodePair(aspect) {
  const a = aspect.planet1;
  const b = aspect.planet2;
  return (a === 'North Node' && b === 'South Node') || (a === 'South Node' && b === 'North Node');
}
