/**
 * ragChatApi.js — два запроса чата с Аристеей и больше ничего.
 *
 *   1. GET  /api/v1/chart/{id}/rag-chat/history — диалог, который помнит сервер;
 *   2. POST /api/v1/chart/{id}/rag-chat         — вопрос, ответ приходит SSE.
 *
 * ⚠️ `EventSource` непригоден, и это не выбор: он умеет только GET, а вопрос
 * уходит телом. Тот же случай, что у разбора транзита, — поэтому чтение потока
 * взято оттуда (`transitInterpretApi.js`): `drainLines` уже написан и покрыт
 * тестами, копировать его в третий раз незачем.
 *
 * ⚠️ **А вот `parseLine` оттуда переиспользовать НЕЛЬЗЯ, и это главная ловушка
 * этого файла.** Формат кадров у двух ручек совпадает до символа, но смысл поля
 * `error` разный:
 *
 *   · у транзита в `error` лежит ЧЕЛОВЕЧЕСКИЙ текст, и та функция правильно
 *     отдаёт его наружу как есть;
 *   · у чата в `error` лежит МАШИННЫЙ код (`empty_response`, `timeout`,
 *     `stream_failed`), а человеческий текст — в соседнем поле `text`
 *     (`backend/interpretation/rag_router.py`).
 *
 * `parseLine` транзита проверяет `error` первым и `text` из того же кадра
 * выбрасывает. Скопированный как есть, он показал бы человеку строку
 * `stream_failed`. Поэтому здесь свой `parseChatLine`, который забирает оба
 * поля, а решение по коду принимает `chatRules.js`.
 *
 * ⚠️ Только `authFetchWithTimeout`. Вебовский чат (`RagChat.jsx`) ходит голым
 * `fetch` с токеном из `localStorage` мимо `authFetch` — единственное такое
 * место в проекте. В приложении это ровно тот капкан холодного старта, ради
 * которого писались гейт по сроку токена и пауза после неудачного обновления
 * (CLAUDE.md, «Холодный старт упирается в ЗАДЕРЖИВАЮЩИЙ лимит»): запрос с
 * заведомо протухшим токеном не должен отправляться вовсе.
 *
 * ⚠️ `history` в теле НЕ шлём. Сервер её игнорирует намеренно — поле оставлено
 * для совместимости со старым фронтом, а сама история переехала на сервер после
 * того, как через поданные клиентом реплики с role="assistant" вытаскивали
 * системный промпт и базу знаний (докстринг `RagChatRequest`).
 */

import { API_BASE } from '../../config';
import { responseErrorText } from '../../api/client';
import { authFetchWithTimeout } from './authFetchTimeout';
import { drainLines } from './transitInterpretApi';

/**
 * Клиентская страховка поверх серверного потолка в 45 секунд
 * (`CHAT_STREAM_TIMEOUT`, rag_router.py).
 *
 * ⚠️ Заведомо БОЛЬШЕ серверного, и это важнее, чем кажется: сдайся клиент
 * раньше сервера — человек увидел бы ошибку по запросу, который на самом деле
 * успешно завершился бы, а расход при этом уже списан. Число и довод взяты у
 * веба (`RagChat.jsx`), где они выведены из того же серверного потолка.
 *
 * Общее умолчание в 15 секунд здесь не годится по той же причине, что у
 * построения карты и разбора транзита: оно описывает, сколько экран ждёт
 * ЗАВИСШУЮ сеть, а тут долгое ожидание — норма (классификатор темы делает
 * отдельный вызов модели ДО начала потока).
 */
export const CHAT_TIMEOUT_MS = 60000;

/** Отдельный, короткий предел для истории: это обычный GET из Redis. */
export const CHAT_HISTORY_TIMEOUT_MS = 15000;

/** Ошибка запроса с кодом и текстом сервера — их разбирает `classifyChatError`. */
export class ChatError extends Error {
  constructor(message, status, detail) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

/**
 * Достаёт `detail` из тела отказа.
 *
 * ⚠️ У 403 этой ручки `detail` — ОБЪЕКТ (`{error, required, current}`,
 * `require_tier`), а не строка. Показывать его человеку нечем, и текст пишется
 * на клиенте (`chatRules.js`). У 429/503/404/400 — обычная строка. Поэтому
 * строкой отдаём только строку, всё остальное — пустая строка, а не
 * «[object Object]» в пузырьке.
 */
async function detailOf(resp) {
  const body = await resp.json().catch(() => null);
  return typeof body?.detail === 'string' ? body.detail : '';
}

/**
 * Диалог, который помнит сервер по этой карте.
 *
 * Копии на клиенте нет намеренно (решение владельца): единственный источник —
 * сервер, иначе завёлся бы второй, расходящийся с ним при каждой смене
 * устройства. История там живёт 6 часов бездействия и обрезана десятью
 * репликами — то есть пустой ответ это нормальный, а не исключительный случай.
 *
 * @returns {Promise<Array<{role: 'user'|'assistant', content: string}>>}
 */
export async function fetchChatHistory(chartId) {
  const resp = await authFetchWithTimeout(
    `${API_BASE}/chart/${chartId}/rag-chat/history`,
    undefined,
    CHAT_HISTORY_TIMEOUT_MS,
  );
  if (!resp.ok) {
    const detail = await detailOf(resp);
    throw new ChatError(
      detail || 'Не удалось загрузить переписку.',
      resp.status,
      detail,
    );
  }
  const data = await resp.json();
  return Array.isArray(data?.messages) ? data.messages : [];
}

/**
 * Разбирает одну строку SSE чата. `null` — строка не несёт полезного.
 *
 * Отличие от `parseLine` транзита — в кадре ошибки: забираем И код, И текст.
 * См. предупреждение в шапке файла.
 */
export function parseChatLine(line) {
  if (!line.startsWith('data: ')) return null;
  const raw = line.slice(6).trim();
  if (!raw) return null;
  if (raw === '[DONE]') return { type: 'done' };
  try {
    const payload = JSON.parse(raw);
    if (payload?.error) {
      return { type: 'error', code: payload.error, text: payload.text || '' };
    }
    if (payload?.text) return { type: 'text', text: payload.text };
    return null;
  } catch {
    // Не JSON — на этой ручке не встречается, но глотать молча нельзя.
    return { type: 'text', text: raw };
  }
}

/**
 * Задаёт вопрос и стримит ответ.
 *
 * @param {string} chartId
 * @param {string} question
 * @param {{onText: (t: string) => void}} handlers
 * @returns {Promise<void>} завершается по `[DONE]` или концу тела
 * @throws {ChatError} — до потока со статусом, внутри потока с кодом в `detail`
 */
export async function streamChatAnswer(chartId, question, { onText }) {
  const resp = await authFetchWithTimeout(
    `${API_BASE}/chart/${chartId}/rag-chat`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
    },
    CHAT_TIMEOUT_MS,
  );

  if (!resp.ok) {
    const detail = await detailOf(resp);
    throw new ChatError(detail || `HTTP ${resp.status}`, resp.status, detail);
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    // stream: true — символ, разорванный между чтениями, дособирается,
    // а не превращается в «замену» (U+FFFD). Русский текст многобайтовый.
    buffer += decoder.decode(value, { stream: true });

    const [lines, tail] = drainLines(buffer);
    buffer = tail;

    for (const line of lines) {
      const parsed = parseChatLine(line);
      if (!parsed) continue;
      if (parsed.type === 'done') return;
      if (parsed.type === 'error') {
        // Код — в detail: по нему `classifyChatError` решает, можно ли
        // повторить. Текст сервера тоже несём, он человеческий.
        throw new ChatError(parsed.text, undefined, parsed.code);
      }
      onText(parsed.text);
    }
  }

  // Тело кончилось без [DONE] — хвост мог остаться цельной строкой.
  const parsed = parseChatLine(buffer.trim());
  if (parsed?.type === 'text') onText(parsed.text);
}
