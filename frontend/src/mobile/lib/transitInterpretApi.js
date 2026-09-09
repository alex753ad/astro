/**
 * transitInterpretApi.js — поток разбора одного транзитного события.
 *
 * Ручка — `POST /api/v1/chart/{id}/transits/event/interpret`
 * (`backend/main.py`). Отвечает SSE-кадрами, но именно POST'ом.
 *
 * ⚠️ Транспорт натального разбора здесь НЕ переиспользуется, и это не выбор, а
 * следствие: `EventSource` умеет только GET. Значит не нужны ни одноразовый
 * тикет (заголовки шлёт обычный `fetch`), ни `_connectSSE` с его реконнектами.
 * Читаем тело через `getReader()`.
 *
 * ⚠️ Кадр SSE может разрезаться между чтениями, и буфер здесь именно поэтому.
 * Вебовский `TransitTimeline.jsx` режет каждое чтение по `\n` НА МЕСТЕ, без
 * буфера между ними: кадр, разорванный посередине, там теряется молча. Это тот
 * же класс дефекта, что уже ловили с `flushBuffer` в натальном разборе, —
 * поэтому строки оттуда не копировались.
 *
 * ⚠️ И вторая причина не копировать: там `dec.decode(value)` без
 * `{ stream: true }`. Русский текст в UTF-8 многобайтовый, и символ,
 * разорванный между чтениями, превращается в «замену» (U+FFFD). Здесь декодер
 * потоковый. Веб этим дефектом задет, но правится отдельно — не молча.
 *
 * ⚠️ Секций в транзитном тексте нет: сервер не передаёт `_SECTION_TAG_RE` в
 * `replay_as_stream` для этой ручки. `lib/sectionStream.js` не подключаем —
 * ему тут нечего разбирать.
 */

import { API_BASE } from '../../config';
import { authFetchWithTimeout } from './authFetchTimeout';

/**
 * Свой предел ожидания, а не общие 15 секунд.
 *
 * Долгая работа здесь норма, а не признак зависания: на промах мимо кэша
 * сервер считает точные факты транзита через Swiss Ephemeris и ходит в модель.
 * Общее умолчание описывает, сколько экран готов ждать ЗАВИСШУЮ сеть, и
 * поднимать его ради одного долгого запроса нельзя — тот же довод, что у
 * построения карты (SPEC_CHART_CREATE.md §9).
 */
export const TRANSIT_INTERPRET_TIMEOUT_MS = 60000;

/**
 * Тело запроса. Все четыре поля обязательны — без `peak_date` ручка отвечает
 * 422 (`main.py`).
 *
 * ⚠️ `peak_date` берётся из `meta` ленты и НЕ выводится из `at`. Своей
 * арифметики дат здесь нет намеренно: `at` — локальный ISO момента
 * `exact_date`, а `peak_date` — дата пика в UTC, и у события около полуночи
 * они расходятся на сутки. На боевых данных 09.09.2026 таких 15 из 278.
 * Дата входит в ключ кэша разбора и в аргумент `compute_exact_facts`, поэтому
 * промах на сутки означает мимо готового кэша: лишняя генерация и лишняя
 * единица из трёх на Веге — при внешне исправном экране.
 */
export function buildTransitBody(event) {
  const meta = event?.meta || {};
  return {
    transit_planet: meta.transit_planet,
    natal_planet: meta.natal_planet,
    aspect_type: meta.aspect_type,
    peak_date: meta.peak_date,
  };
}

/** Всё ли есть для запроса. Без этого 422 приедет уже с сервера. */
export function canInterpretTransit(event) {
  const body = buildTransitBody(event);
  return Boolean(
    body.transit_planet && body.natal_planet && body.aspect_type && body.peak_date,
  );
}

/**
 * Ошибка запроса с кодом и текстом сервера — их разбирает
 * `classifyTransitError`.
 */
export class TransitInterpretError extends Error {
  constructor(message, status, detail) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

/**
 * Разбирает накопленный буфер на цельные строки.
 *
 * Возвращает `[строки, остаток]`. Остаток — незавершённая строка, которую
 * дочитает следующее чтение; именно её терял вебовский разборщик.
 */
export function drainLines(buffer) {
  const parts = buffer.split('\n');
  const tail = parts.pop();          // последняя часть может быть неполной
  return [parts, tail];
}

/**
 * Разбирает одну строку SSE. Возвращает `null` для всего, что не data-строка.
 * `[DONE]` отдаётся отдельным видом — по нему поток считается завершённым.
 */
export function parseLine(line) {
  if (!line.startsWith('data: ')) return null;
  const raw = line.slice(6).trim();
  if (!raw) return null;
  if (raw === '[DONE]') return { type: 'done' };
  try {
    const payload = JSON.parse(raw);
    if (payload?.error) return { type: 'error', error: payload.error };
    if (payload?.text) return { type: 'text', text: payload.text };
    return null;
  } catch {
    // Не JSON — на этой ручке не встречается, но глотать молча нельзя:
    // пусть придёт текстом, а не исчезнет.
    return { type: 'text', text: raw };
  }
}

/**
 * Запускает разбор транзита.
 *
 * @param {string} chartId
 * @param {object} event — событие ленты (нужен только `meta`)
 * @param {{onText: (t: string) => void}} handlers
 * @returns {Promise<void>} завершается по `[DONE]` или концу тела
 * @throws {TransitInterpretError}
 */
export async function streamTransitInterpretation(chartId, event, { onText }) {
  const resp = await authFetchWithTimeout(
    `${API_BASE}/chart/${chartId}/transits/event/interpret`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(buildTransitBody(event)),
    },
    TRANSIT_INTERPRET_TIMEOUT_MS,
  );

  if (!resp.ok) {
    // Текст сервера достаём здесь, а решение по нему принимает
    // classifyTransitError — тексты 403 и 429 законченные и показываются
    // дословно.
    const body = await resp.json().catch(() => null);
    const detail = typeof body?.detail === 'string' ? body.detail : '';
    throw new TransitInterpretError(detail || `HTTP ${resp.status}`, resp.status, detail);
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    // stream: true — символ, разорванный между чтениями, дособирается,
    // а не превращается в «замену».
    buffer += decoder.decode(value, { stream: true });

    const [lines, tail] = drainLines(buffer);
    buffer = tail;

    for (const line of lines) {
      const parsed = parseLine(line);
      if (!parsed) continue;
      if (parsed.type === 'done') return;
      if (parsed.type === 'error') {
        // Исключение внутри генерации. Расход при этом не списан —
        // commit_transit_ai стоит после полностью выданного текста.
        throw new TransitInterpretError(parsed.error, undefined, parsed.error);
      }
      onText(parsed.text);
    }
  }

  // Тело кончилось без [DONE] — хвост буфера мог остаться цельной строкой.
  const parsed = parseLine(buffer.trim());
  if (parsed?.type === 'text') onText(parsed.text);
}
