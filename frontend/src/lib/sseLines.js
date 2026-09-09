/**
 * sseLines.js — чтение SSE-потока, полученного обычным `fetch`.
 *
 * Нужен там, где `EventSource` непригоден: он умеет только GET, а разбор
 * транзита живёт на `POST /chart/{id}/transits/event/interpret`. Общий файл
 * для веба и мобильного клиента — по образцу `lib/sectionStream.js`.
 *
 * ⚠️ Здесь два предохранителя, и оба поставлены не «на всякий случай»: без
 * каждого из них текст портился молча, и в вебе он портился до 09.09.2026.
 *
 * **1. Потоковый декодер (`{ stream: true }`).** Русский текст в UTF-8
 * многобайтовый. Сеть режет поток по байтам, а не по символам, и буква,
 * разорванная между двумя чтениями, при `decode(value)` без флага
 * превращается в «замену» — ромбик с вопросом. Дефект плавающий: граница
 * чтений зависит от размера пакетов, поэтому на коротких ответах его можно
 * не увидеть месяцами.
 *
 * **2. Буфер между чтениями.** SSE-кадр (`data: {...}\n`) может быть разорван
 * посередине. Разбор «на месте», где каждое чтение режется по переводу строки
 * и остаток выбрасывается, теряет такой кадр целиком — то есть кусок текста
 * пропадает, а поток продолжается как ни в чём не бывало. Тот же класс
 * дефекта, что ловили с `flushBuffer` в разборе натальной карты: приёмная
 * сторона теряет данные, а выглядит исправной.
 *
 * ⚠️ Разбирать `<section>`-разметку здесь нечего: у транзитной ручки её нет
 * (сервер не передаёт `_SECTION_TAG_RE` в `replay_as_stream`). Для натального
 * разбора есть отдельный `lib/sectionStream.js` — не путать.
 */

/**
 * Делит накопленный буфер на цельные строки.
 * @returns {[string[], string]} строки и остаток — незавершённую строку,
 *          которую дочитает следующее чтение. Именно её теряет разбор без
 *          буфера.
 */
export function splitLines(buffer) {
  const parts = buffer.split('\n');
  const tail = parts.pop();
  return [parts, tail];
}

/**
 * Разбирает одну строку SSE.
 * @returns {null | {type: 'text', text: string} | {type: 'done'} | {type: 'error', error: string}}
 */
export function parseSseLine(line) {
  if (!line.startsWith('data: ')) return null;   // комментарии, event:, пустые
  const raw = line.slice(6).trim();
  if (!raw) return null;
  if (raw === '[DONE]') return { type: 'done' };
  try {
    const payload = JSON.parse(raw);
    if (payload?.error) return { type: 'error', error: payload.error };
    if (payload?.text) return { type: 'text', text: payload.text };
    return null;
  } catch {
    // Не JSON. На наших ручках не встречается, но проглотить молча нельзя:
    // пусть доедет текстом, чем исчезнет.
    return { type: 'text', text: raw };
  }
}

/**
 * Читает тело ответа и отдаёт разобранные события по мере поступления.
 *
 * @param {ReadableStream} body — `response.body`
 * @yields {{type: 'text'|'done'|'error', text?: string, error?: string}}
 *
 * Вызывающая сторона решает, что делать с `done` и `error`: у веба и
 * мобильного клиента разные экраны и разные правила показа отказа.
 */
export async function* readSseLines(body) {
  const reader = body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const [lines, tail] = splitLines(buffer);
    buffer = tail;
    for (const line of lines) {
      const ev = parseSseLine(line);
      if (ev) yield ev;
    }
  }

  // Поток кончился без перевода строки в конце — остаток может быть цельной
  // строкой. Плюс добираем хвост декодера (незавершённая последовательность).
  buffer += decoder.decode();
  const ev = parseSseLine(buffer.trim());
  if (ev) yield ev;
}
