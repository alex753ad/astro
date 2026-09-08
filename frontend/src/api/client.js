/**
 * API client for Aristea Timeline backend.
 *
 * Handles:
 * - REST calls (chart, transits)
 * - SSE streaming (AI interpretations) with Last-Event-ID reconnect
 * - Error handling with retry
 */

import { API_BASE } from '../config';
import { isTokenExpired } from '../lib/jwt';
import { createSectionParser } from '../lib/sectionStream';
import {
  AUTH_CREDENTIALS,
  authRequestBody,
  clientHeaders,
  forgetRefreshToken,
  rememberRefreshToken,
} from './authTransport';
import { diag } from '../lib/authDiag';

class ApiError extends Error {
  constructor(message, status, detail) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

/**
 * Текст ошибки для пользователя.
 *
 * Бэкенд формулирует detail по-русски и по делу («Тариф Орион пока не
 * продаётся», «Вы использовали бесплатную интерпретацию. Оформите Вега…»),
 * request() кладёт его в ApiError.message — и раньше всё это выбрасывалось
 * ради одной общей фразы во всех случаях сразу.
 *
 * Показываем detail там, где он есть, то есть когда сервер ответил (у ошибки
 * есть status). Сетевой сбой доезжает сюда TypeError без status и с текстом
 * вида «Failed to fetch» — он на языке браузера, не переводится и
 * пользователю ничего не объясняет, поэтому подменяется запасной фразой.
 */
export function apiErrorText(err, fallback) {
  return typeof err?.status === 'number' && err.message ? err.message : fallback;
}

/**
 * То же, но для потоковых ответов, которые читаются вручную через
 * resp.body.getReader() и мимо request() — там ApiError не создаётся, а
 * непрочитанный detail просто пропадает.
 *
 * Тело читается ОДИН раз и только при !resp.ok: у Response тело одноразовое,
 * и вызвать json() после getReader() (или наоборот) уже нельзя.
 *
 * detail не всегда строка: часть эндпоинтов отдаёт объект вида
 * {error: "tier_required", required: "pro"} — его пользователю показывать
 * нечего, поэтому такие случаи уходят в запасной текст со статусом.
 */
export async function responseErrorText(resp, fallback = 'Не удалось загрузить.') {
  let detail;
  try {
    detail = (await resp.json())?.detail;
  } catch {
    // тело не JSON или пустое — сказать нечего
  }
  if (typeof detail === 'string' && detail.trim()) return detail;
  return resp.status ? `${fallback} (${resp.status})` : fallback;
}

const ACCESS_TOKEN_KEY  = 'astro_access_token';
// Refresh-токена здесь больше нет: он живёт в HttpOnly-куке astro_refresh,
// которую JS не читает и не пишет. Раньше он лежал в localStorage и жил 7 дней —
// то есть любой XSS (или скомпрометированная зависимость в бандле) уносил
// недельный доступ к аккаунту. Access-токен остаётся в localStorage: он живёт
// 15 минут и нужен как заголовок в каждом запросе.
const LEGACY_REFRESH_KEY = 'astro_refresh_token';

// ═══════════════════════════════════════════════════════════
// ОБНОВЛЕНИЕ СЕССИИ — ЕДИНСТВЕННЫЙ КОНТУР НА ВСЁ ПРИЛОЖЕНИЕ
// ═══════════════════════════════════════════════════════════
//
// ⚠️ До 07.09.2026 контуров было ДВА: этот и свой собственный в
// hooks/useAuth.jsx (attemptRefresh с отдельным refreshInFlightRef). Они не
// знали друг о друге, и это ломало сессию на устройстве — разбор по следам
// приёмки регистрации:
//
//   1. оба контура берут ОДИН И ТОТ ЖЕ refresh (из нативного хранилища) и
//      могут отправить его параллельно — таймер useAuth и запрос экрана;
//   2. сервер ротирует токен: первому выдаёт новую пару, второму отвечает
//      401 «Refresh token уже использован» (reuse-detection,
//      backend/auth/router.py);
//   3. проигравший считал это смертью сессии и вызывал forgetRefreshToken()
//      — СТИРАЛ свежий refresh, который победитель только что записал;
//   4. access при этом оставался свежим ещё до 15 минут: приложение
//      выглядело вошедшим, но обновиться больше не могло никогда.
//
// Лечится не «синхронизацией двух контуров», а тем, что контур один: здесь.
// useAuth.jsx вызывает эту же функцию и на неё же подписывается.
//
// Дедуп внутри контура (refreshInFlight) остаётся обязательным по той же
// причине из п.2: два параллельных 401 не должны слать refresh дважды.
let refreshInFlight = null;

// Пауза после НЕУДАЧНОГО обновления (кроме отказа в аутентификации — там уже
// разлогин, повторять нечего).
//
// Без неё приложение само себя топит на холодном старте. TabShell монтирует
// все три экрана разом, каждый шлёт свои запросы с уже протухшим access —
// значит первый залп 401 сходится в один refresh (дедуп выше), но КАЖДЫЙ
// следующий залп (повтор экрана, нажатие «Повторить», переход по вкладке)
// заводит новую попытку. А /api/v1/auth/ на проде стоит за задерживающим
// лимитом nginx (zone=auth, 1 r/s на адрес, burst=10 БЕЗ nodelay): запросы не
// отбиваются, а ВЫСТРАИВАЮТСЯ В ОЧЕРЕДЬ по секунде на каждый. Замер
// 07.09.2026 на боевом сервере: 12 параллельных /auth/refresh ответили через
// 1.9, 2.9, 3.9 … 11.9 с, один получил 429. То есть чем чаще клиент
// повторяет, тем дольше отвечает сервер — и экраны упираются в свой
// 15-секундный таймаут («Сервер не отвечает», mobile/lib/authFetchTimeout.js).
//
// Окно короткое: оно гасит именно ЗАЛП, а не осмысленный повтор через паузу.
const REFRESH_COOLDOWN_MS = 5000;

/**
 * Предел ожидания одного обновления сессии.
 *
 * До 08.09.2026 его не было вовсе: у fetch к /auth/refresh не стояло ни
 * таймаута, ни AbortController. Зависший запрос (мёртвый сокет после долгого
 * фона — тот же случай, что описан в шапке mobile/lib/authFetchTimeout.js) не
 * отклонялся никогда, а значит `refreshInFlight` ниже оставался заполненным
 * навсегда: КАЖДЫЙ следующий вызов получал тот же неразрешающийся промис и
 * молчал. Один зависший запрос выключал обновление сессии целиком — и таймер,
 * и возврат из фона, и повтор по 401.
 *
 * ⚠️ Abort закрывает сам сетевой запрос, но НЕ чтение refresh-токена из
 * нативного хранилища: оно уходит через мост Capacitor до начала fetch, и
 * прервать его сигналом нечем. Зависание там даст ровно тот же симптом, а
 * лечится иначе — поэтому оно отдельно размечено отметками
 * 'storage:read' / 'storage:read:done' в api/authTransport.js.
 *
 * 15 с — столько же, сколько экранный таймаут (REQUEST_TIMEOUT_MS): меньше
 * значило бы обрывать обновления, которые ещё могли успеть, больше — экран
 * всё равно сдастся раньше и число здесь ни на что не повлияет.
 */
const REFRESH_TIMEOUT_MS = 15000;
let lastRefreshFailure = null; // { at, result }

// Подписчики на события сессии. Нужны, чтобы client.js (модуль без React) мог
// сообщить владельцу состояния (useAuth) о том, что сессия кончилась, — и
// решение о разлогине принималось В ОДНОМ месте, а не в каждой точке вызова.
const sessionExpiredHandlers = new Set();
const tokensRefreshedHandlers = new Set();

function notify(handlers, arg) {
  for (const handler of [...handlers]) {
    try { handler(arg); } catch { /* подписчик не должен ломать обновление */ }
  }
}

/**
 * Запомнить неудачу, чтобы следующие несколько секунд отвечать ею сразу, без
 * запроса. Отказ аутентификации сюда НЕ попадает: он уже привёл к разлогину,
 * а закэшированный 'auth' пережил бы вход и сломал только что выданную пару.
 */
function rememberFailure(result) {
  lastRefreshFailure = { at: Date.now(), result };
  return result;
}

/** Сессия кончилась по ЯВНОМУ отказу сервера. Не вызывается при сетевых сбоях. */
export function onSessionExpired(handler) {
  sessionExpiredHandlers.add(handler);
  return () => sessionExpiredHandlers.delete(handler);
}

/** Токены обновлены — пришла новая пара. */
export function onTokensRefreshed(handler) {
  tokensRefreshedHandlers.add(handler);
  return () => tokensRefreshedHandlers.delete(handler);
}

/**
 * Обновить пару токенов.
 *
 * Возвращает результат, а не бросает, потому что вызывающим важно РАЗЛИЧАТЬ
 * причины — от этого зависит, выкидывать ли человека на экран входа:
 *
 *   { ok: true, data }               — обновились;
 *   { ok: false, reason: 'auth' }    — сервер отказал в аутентификации (401/403):
 *                                      refresh мёртв, отозван или его нет.
 *                                      Сессии больше нет — это разлогин;
 *   { ok: false, reason: 'network' } — запрос не дошёл (самолётный режим,
 *                                      обрыв, таймаут). Сессия, возможно, жива;
 *   { ok: false, reason: 'server' }  — сервер ответил, но не отказом в доступе
 *                                      (429 от лимитера, 5xx). Тоже НЕ разлогин.
 *
 * ⚠️ Разница между 'auth' и остальными — не косметика. Выкидывать на экран
 * входа при потере связи нельзя: человек в метро потеряет сессию на ровном
 * месте, хотя достаточно было показать «Повторить».
 */
export async function refreshSession() {
  if (refreshInFlight) return refreshInFlight;
  if (lastRefreshFailure && Date.now() - lastRefreshFailure.at < REFRESH_COOLDOWN_MS) {
    return lastRefreshFailure.result;
  }

  const attempt = (async () => {
    diag('refresh:start');
    const controller = new AbortController();
    const abortTimer = setTimeout(() => controller.abort(), REFRESH_TIMEOUT_MS);
    let resp;
    try {
      resp = await fetch(`${API_BASE}/auth/refresh`, {
        signal: controller.signal,
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...clientHeaders() },
        // credentials: кука astro_refresh едет только явно — по умолчанию
        // fetch её не отправляет, если API на другом origin. На устройстве
        // куки нет, и токен уезжает в теле — см. authTransport.js.
        credentials: AUTH_CREDENTIALS,
        body: await authRequestBody(),
      });
    } catch {
      // Сюда попадают и сетевые сбои, и недоступное нативное хранилище.
      // ⚠️ Хранилище НЕ трогаем: сессия могла остаться живой, а стереть
      // refresh здесь — это ровно тот дефект, из-за которого приложение
      // застревало с мёртвым токеном (см. шапку раздела).
      diag('refresh:end', 'network — обрыв, недоступное хранилище или таймаут');
      return rememberFailure({ ok: false, reason: 'network' });
    } finally {
      // Таймер снимается в любом исходе: иначе он держал бы приложение
      // разбуженным на 15 с после каждого успешного обновления.
      clearTimeout(abortTimer);
    }

    if (!resp.ok) {
      diag('refresh:end', `HTTP ${resp.status}`);
      if (resp.status !== 401 && resp.status !== 403) {
        // 429 от лимитера, 5xx — сервер жив, но сейчас не отвечает по делу.
        // Сессию не хороним: следующая попытка может пройти.
        return rememberFailure({ ok: false, reason: 'server' });
      }
      // Явный отказ аутентификации — refresh мёртв, отозван или не предъявлен.
      localStorage.removeItem(ACCESS_TOKEN_KEY);
      localStorage.removeItem(LEGACY_REFRESH_KEY);
      try { await forgetRefreshToken(); } catch { /* хранилище недоступно */ }
      notify(sessionExpiredHandlers);
      return { ok: false, reason: 'auth' };
    }

    let data;
    try {
      data = await resp.json();
    } catch {
      diag('refresh:end', 'ответ 200, но тело не разобрано');
      return rememberFailure({ ok: false, reason: 'server' });
    }
    diag('refresh:end', 'ok');

    lastRefreshFailure = null;

    localStorage.setItem(ACCESS_TOKEN_KEY, data.access_token);
    // Сервер ротирует refresh: не сохранив новый, приложение разлогинится на
    // следующем обновлении. В вебе это no-op — там refresh в куке.
    await rememberRefreshToken(data);
    // Подчищаем хвост от прошлой схемы: у вернувшихся пользователей старый
    // refresh может лежать в localStorage ещё неделю.
    localStorage.removeItem(LEGACY_REFRESH_KEY);
    notify(tokensRefreshedHandlers, data);
    return { ok: true, data };
  })();

  refreshInFlight = attempt;
  // Освобождение — в finally, а не в ветках выше: у промиса выше семь путей
  // выхода, и достаточно одного, где обновление забыли бы снять, чтобы
  // контур замолчал навсегда. finally покрывает и исключение, которого
  // сегодня нет, но может появиться при следующей правке.
  attempt.finally(() => {
    if (refreshInFlight === attempt) refreshInFlight = null;
  });
  return attempt;
}

/**
 * fetch с авторизацией и однократным повтором после обновления токена.
 *
 * Access-токен живёт 15 минут. Без этого повтора протухший токен приводил к
 * ошибке на экране: сервер отвечает 401, а клиент не пытался обновиться.
 * Принимает абсолютный URL — используется и из client.js, и со страниц с
 * собственным базовым адресом.
 */
export async function authFetch(url, options = {}) {
  const send = (token) => fetch(url, {
    ...options,
    headers: {
      ...(options.headers || {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  });

  let token = localStorage.getItem(ACCESS_TOKEN_KEY);

  // Заведомо мёртвый токен не отправляем: обновляемся ДО запроса.
  //
  // ⚠️ Это не оптимизация, а лечение залпа на холодном старте. TabShell
  // монтирует все три экрана разом, и каждый шлёт свои запросы с одним и тем
  // же протухшим токеном. Без этой ветки старт выглядел так: N обречённых
  // запросов → N ответов 401 → одно обновление (дедуп refreshInFlight) →
  // N повторов, то есть 2N+1 запросов вместо N+1, и часть из них — в
  // задерживающей зоне лимитера (/auth/me). Дедуп и пауза этого не решают:
  // они схлопывают ПОВТОРНЫЕ обновления, а сам залп создают экраны.
  // Четвёртый экран удлинил бы залп ровно на столько же.
  //
  // Здесь же оно чинится один раз для всех — и для тех экранов, которых ещё
  // нет: параллельные вызовы сходятся в один refreshSession, ждут его и
  // уходят уже с живым токеном.
  if (token && isTokenExpired(token)) {
    diag('gate:expired', url);
    const ahead = await refreshSession();
    if (ahead.ok) token = ahead.data.access_token;
    // Не вышло — отправляем как есть. Сервер скажет своё 401, а решение о
    // судьбе сессии остаётся единственным и лежит в refreshSession.
  }

  let resp = await send(token);

  if (resp.status === 401 && token) {
    diag('401', url);
    const result = await refreshSession();
    if (result.ok) resp = await send(result.data.access_token);
    // Отдельной ветки на result.reason === 'auth' здесь нет намеренно:
    // разлогин — единственная точка, и она внутри refreshSession
    // (notify sessionExpiredHandlers → logout в useAuth). Дублировать
    // решение здесь значило бы завести второе место, где приложение решает
    // судьбу сессии, — ровно то, из-за чего был весь дефект.
    // При 'network'/'server' возвращаем исходный 401: экран покажет ошибку
    // с «Повторить», человек останется в аккаунте.
  }

  return resp;
}

async function request(path, options = {}) {
  const url = `${API_BASE}${path}`;
  const resp = await authFetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  });

  if (!resp.ok) {
    const body = await resp.json().catch(() => ({ detail: resp.statusText }));
    let msg = body.detail || resp.statusText;
    if (Array.isArray(msg)) msg = msg.map(e => e.msg?.replace(/^Value error, /, '') ?? JSON.stringify(e)).join('; ');
    throw new ApiError(msg, resp.status, body);
  }

  return resp.json();
}

// ── Chart API ──

export async function calculateChart(birthData) {
  return request('/chart/calculate', {
    method: 'POST',
    body: JSON.stringify(birthData),
  });
}

export async function saveAnonymousChart(birthData) {
  return request('/chart/save-anonymous', {
    method: 'POST',
    body: JSON.stringify(birthData),
  });
}

export async function getChart(chartId) {
  return request(`/chart/${chartId}`);
}

// ── SSE Streaming ──

/**
 * Меняет access-токен на одноразовый тикет для EventSource.
 *
 * Сам access-токен в query класть нельзя: URL оседает в логах прокси, Referer
 * и истории браузера. Тикет живёт ~минуту и гасится при первом использовании,
 * поэтому запрашивается заново на каждое подключение (включая реконнекты).
 * Возвращает null для анонима — SSE-эндпоинты доступны и без авторизации.
 */
async function _sseTicket() {
  const token = localStorage.getItem('astro_access_token');
  if (!token) return null;
  try {
    const resp = await fetch(`${API_BASE}/auth/sse-ticket`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!resp.ok) return null;
    return (await resp.json()).ticket ?? null;
  } catch {
    return null;
  }
}

function _connectSSE(buildUrl, onChunk, onDone, onError) {
  let lastEventId = null;
  let hasData     = false;
  let isDone      = false;
  let attempt     = 0;
  let eventSource = null;
  let retryTimeout = null;
  let cancelled   = false;
  const maxRetries = 3;

  // Разбор разметки <section> живёт в общем файле lib/sectionStream.js —
  // он однопроходный и одинаково переживает все три пути отдачи
  // (INTERPRET_SSE_RECON.md). Прежний локальный flushBuffer разбирал буфер
  // двумя проходами и придерживал незакрытый хвост по порогу длины в 19
  // символов — короче открывающего тега, из-за чего на живой генерации
  // section_start не приходил вовсе.
  //
  // Экземпляр пересоздаётся на каждое подключение (в connect()): у парсера
  // есть состояние между событиями — недоразобранный хвост и открытая
  // секция, — а докачки у ручки нет, после обрыва поток начинается сначала.
  let parser = createSectionParser();

  async function connect() {
    const url = await buildUrl();
    if (cancelled) return;

    // Реконнект начинает поток с нуля, поэтому и разбор начинается с нуля:
    // хвост и открытая секция от оборванной попытки иначе склеились бы с
    // началом новой.
    parser = createSectionParser();

    const connectUrl = lastEventId
      ? url + (url.includes('?') ? '&' : '?') + 'last_event_id=' + encodeURIComponent(lastEventId)
      : url;

    eventSource = new EventSource(connectUrl);

    eventSource.onmessage = (event) => {
      if (event.lastEventId) lastEventId = event.lastEventId;

      if (event.data === '[DONE]') {
        // Финальный сброс: остаток хвоста и закрытие секции, если модель
        // не дописала </section> (обрезка по длине — легальный случай).
        for (const ev of parser.end()) onChunk(ev);
        isDone = true;
        eventSource.close();
        onDone?.();
        return;
      }
      try {
        const parsed = JSON.parse(event.data);
        if (parsed.type === 'section_start' || parsed.type === 'section_end') {
          onChunk({ type: parsed.type, name: parsed.name });
        } else if (parsed.text) {
          hasData = true;
          for (const ev of parser.push(parsed.text)) onChunk(ev);
        }
        if (parsed.error) {
          onError?.(parsed.error);
          eventSource.close();
        }
      } catch { /* skip */ }
    };

    eventSource.onerror = () => {
      eventSource.close();

      if (isDone) { onDone?.(); return; }

      if (attempt < maxRetries) {
        const delay = 1500 * (attempt + 1);
        console.warn(`SSE connection lost. Reconnect attempt ${attempt + 1}/${maxRetries} in ${delay}ms…`);
        attempt++;
        retryTimeout = setTimeout(connect, delay);
      } else {
        if (hasData) { onDone?.(); } else { onError?.('Connection lost'); }
      }
    };
  }

  connect();

  return () => {
    cancelled = true;
    clearTimeout(retryTimeout);
    eventSource?.close();
  };
}

export function streamInterpretation(chartId, onChunk, onDone, onError) {
  const buildUrl = async () => {
    const ticket = await _sseTicket();
    const q = ticket ? `?ticket=${encodeURIComponent(ticket)}` : '';
    return `${API_BASE}/chart/${chartId}/interpret${q}`;
  };
  return _connectSSE(buildUrl, onChunk, onDone, onError);
}

// ── Async Tasks API ──

export async function startPdfGeneration(chartId) {
  return request(`/chart/${chartId}/pdf`, { method: 'POST' });
}

export { ApiError };

// ── Payments API ──

// ── Profile / Feature Flags ──

export async function getSubscription(token) {
  return request('/profile/subscription', {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
}

export async function createCheckoutSession(tier, billing, chartId, promoCode = null) {
  const token = localStorage.getItem('astro_access_token');
  const body = { tier, billing_period: billing, chart_id: chartId };
  if (promoCode) body.promo_code = promoCode;
  return request('/payments/checkout', {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: JSON.stringify(body),
  });
}

// ── Соляр / синастрия / релокация (только для админов) ──
//
// Расчёты — обычный request(). Стримы: соляр и релокация это GET, поэтому
// идут через EventSource + одноразовый тикет; синастрия передаёт партнёра в
// теле, поэтому это POST + ReadableStream.
// onChunk во всех трёх получает обычную строку текста.

export async function calculateSolarReturn(chartId, year, location = null) {
  return request(`/chart/${chartId}/solar-return`, {
    method: 'POST',
    body: JSON.stringify({ year, location }),
  });
}

export function streamSolarReturnInterpretation(chartId, year, location, onChunk, onDone, onError) {
  const buildUrl = async () => {
    const ticket = await _sseTicket();
    const params = new URLSearchParams();
    if (location) params.set('location', location);
    if (ticket) params.set('ticket', ticket);
    const qs = params.toString();
    return `${API_BASE}/chart/${chartId}/solar-return/${year}/interpret${qs ? `?${qs}` : ''}`;
  };
  return _connectSSE(buildUrl, (c) => { if (c.type === 'text') onChunk(c.text); }, onDone, onError);
}

export async function calculateSynastry(chartId, partnerData) {
  return request('/chart/synastry', {
    method: 'POST',
    body: JSON.stringify({ chart_id: chartId, partner: partnerData }),
  });
}

export async function streamSynastryInterpretation(chartId, partnerData, onChunk, onDone, onError) {
  try {
    const resp = await authFetch(`${API_BASE}/chart/synastry/interpret`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ chart_id: chartId, partner: partnerData }),
    });

    if (!resp.ok) {
      const body = await resp.json().catch(() => ({}));
      onError?.(body.detail || `Ошибка ${resp.status}`);
      return;
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const data = line.slice(6);
        if (data === '[DONE]') { onDone?.(); return; }
        try {
          const parsed = JSON.parse(data);
          if (parsed.text) onChunk(parsed.text);
          if (parsed.error) onError?.(parsed.error);
        } catch { /* пропускаем неполные фреймы */ }
      }
    }
    onDone?.();
  } catch (err) {
    onError?.(err.message);
  }
}

export async function calculateRelocation(chartId, location) {
  return request(`/chart/${chartId}/relocation`, {
    method: 'POST',
    body: JSON.stringify({ location }),
  });
}

export function streamRelocationInterpretation(chartId, location, onChunk, onDone, onError) {
  const buildUrl = async () => {
    const ticket = await _sseTicket();
    const params = new URLSearchParams({ location });
    if (ticket) params.set('ticket', ticket);
    return `${API_BASE}/chart/${chartId}/relocation/interpret?${params}`;
  };
  return _connectSSE(buildUrl, (c) => { if (c.type === 'text') onChunk(c.text); }, onDone, onError);
}
