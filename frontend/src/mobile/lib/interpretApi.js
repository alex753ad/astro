/**
 * interpretApi.js — запуск потока разбора (SPEC_INTERPRETATION.md §3).
 *
 * Тонкая обёртка вокруг вебовского `streamInterpretation` (`api/client.js`).
 * Своего транспорта здесь нет и не должно быть: тикет, реконнекты и разбор
 * секций уже сделаны там, а разбор секций вдобавок вынесен в общий
 * `lib/sectionStream.js`.
 *
 * ⚠️ Почему это работает в webview — проверено 08.09.2026, а не предположено:
 *   · `EventSource` в Android WebView поддерживается (caniuse `eventsource`,
 *     строка `android` — `y`; для сравнения у `web-share` там `n`);
 *   · CORS для origin `https://localhost` разрешён на БОЕВОМ сервере —
 *     живой запрос возвращает `access-control-allow-origin: https://localhost`.
 *     `EventSource` шлёт простой GET без preflight, этого достаточно;
 *   · заголовки `EventSource` слать не умеет, поэтому авторизация идёт
 *     одноразовым тикетом в query — `_sseTicket` читает access-токен из
 *     `localStorage`, что в мобильном клиенте работает так же, как в вебе.
 *
 * ⚠️ `authFetchWithTimeout` здесь НЕ используется, и это не пропуск: предел
 * ожидания описывает, сколько экран ждёт зависшую сеть, а тут долгая работа
 * — норма (боевой замер: 40.4 с на free, первое событие через 2.5 с). Роль
 * таймаута играет сам поток: пока идут события, ждать есть чего; когда
 * связь рвётся, транспорт сообщает об этом сам.
 */

import { streamInterpretation } from '../../api/client';

/**
 * Запускает поток и раздаёт события экрану.
 *
 * @param {string} chartId
 * @param {{
 *   onSectionStart: (name: string) => void,
 *   onText: (text: string) => void,
 *   onSectionEnd: () => void,
 *   onDone: () => void,
 *   onError: (err: unknown) => void,
 * }} handlers
 * @returns {() => void} закрыть поток
 *
 * ⚠️ Возвращённую функцию обязан вызвать тот, кто открыл поток, — при уходе
 * с экрана и перед КАЖДЫМ повторным запуском. Иначе после перезапроса из
 * фона (§7 спецификации) два открытых `EventSource` будут писать в один
 * экран, и секции перемешаются.
 */
export function startInterpretation(chartId, handlers) {
  return streamInterpretation(
    chartId,
    (chunk) => {
      if (chunk.type === 'section_start') handlers.onSectionStart(chunk.name);
      else if (chunk.type === 'section_end') handlers.onSectionEnd();
      else if (chunk.type === 'text') handlers.onText(chunk.text);
    },
    handlers.onDone,
    handlers.onError,
  );
}
