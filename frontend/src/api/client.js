/**
 * API client for Astrea Timeline backend.
 *
 * Handles:
 * - REST calls (chart, transits)
 * - SSE streaming (AI interpretations) with Last-Event-ID reconnect
 * - Error handling with retry
 */

const API_BASE = 'https://astro-production-abcc.up.railway.app/api/v1';

class ApiError extends Error {
  constructor(message, status, detail) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

async function request(path, options = {}) {
  const url = `${API_BASE}${path}`;
  const token = localStorage.getItem('astro_access_token');
  const resp = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
    ...options,
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

// ── Transit API ──

export async function getTransits(chartId, fromDate, toDate, options = {}) {
  const params = new URLSearchParams({ from_date: fromDate, to_date: toDate });
  if (options.planet) params.set('planet', options.planet);
  if (options.maxOrb) params.set('max_orb', options.maxOrb);
  return request(`/chart/${chartId}/transits?${params}`);
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

  // Буфер для парсинга тегов <section> из потока
  let textBuffer = '';

  function flushBuffer(buffer, final = false) {
    // Ищем теги <section name="..."> и </section>
    const sectionStartRe = /<section name="([^"]+)">\n?/g;
    const sectionEndRe = /<\/section>\n?/g;

    let lastIndex = 0;
    let result = buffer;

    // Обрабатываем буфер целиком через замену
    result = result.replace(/<section name="([^"]+)">\n?/g, (match, name) => {
      onChunk({ type: 'section_start', name });
      return '';
    });
    result = result.replace(/<\/section>\n?/g, () => {
      onChunk({ type: 'section_end' });
      return '';
    });

    // Если не финальный сброс — придерживаем хвост (незакрытый тег)
    if (!final) {
      const lastOpen = result.lastIndexOf('<');
      if (lastOpen !== -1 && lastOpen > result.length - 20) {
        const tail = result.slice(lastOpen);
        result = result.slice(0, lastOpen);
        // возвращаем хвост в буфер
        return { text: result, remaining: tail };
      }
    }
    return { text: result, remaining: '' };
  }

  async function connect() {
    const url = await buildUrl();
    if (cancelled) return;

    const connectUrl = lastEventId
      ? url + (url.includes('?') ? '&' : '?') + 'last_event_id=' + encodeURIComponent(lastEventId)
      : url;

    eventSource = new EventSource(connectUrl);

    eventSource.onmessage = (event) => {
      if (event.lastEventId) lastEventId = event.lastEventId;

      if (event.data === '[DONE]') {
        // Финальный сброс буфера
        if (textBuffer) {
          const { text } = flushBuffer(textBuffer, true);
          if (text) onChunk({ type: 'text', text });
          textBuffer = '';
        }
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
          textBuffer += parsed.text;
          const { text, remaining } = flushBuffer(textBuffer, false);
          textBuffer = remaining;
          if (text) onChunk({ type: 'text', text });
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

export function streamTransitInterpretation(chartId, fromDate, toDate, onChunk, onDone, onError) {
  const buildUrl = async () => {
    const ticket = await _sseTicket();
    const params = new URLSearchParams({ from_date: fromDate, to_date: toDate });
    if (ticket) params.set('ticket', ticket);
    return `${API_BASE}/chart/${chartId}/transits/interpret?${params}`;
  };
  return _connectSSE(buildUrl, onChunk, onDone, onError);
}

export async function streamTransitEventInterpretation(chartId, transitEvent, onChunk, onDone, onError) {
  const url = `${API_BASE}/chart/${chartId}/transits/event/interpret`;

  try {
    const resp = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(transitEvent),
    });

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
        if (line.startsWith('data: ')) {
          const data = line.slice(6);
          if (data === '[DONE]') { onDone?.(); return; }
          try {
            const parsed = JSON.parse(data);
            if (parsed.text) onChunk(parsed.text);
            if (parsed.error) onError?.(parsed.error);
          } catch { /* skip */ }
        }
      }
    }
    onDone?.();
  } catch (err) {
    onError?.(err.message);
  }
}

// ── Async Tasks API ──

export async function startTransitsAsync(chartId, fromDate, toDate, options = {}) {
  const params = new URLSearchParams({ from_date: fromDate, to_date: toDate });
  if (options.planet) params.set('planet', options.planet);
  if (options.maxOrb) params.set('max_orb', options.maxOrb);
  return request(`/chart/${chartId}/transits/async?${params}`, { method: 'POST' });
}

export async function startPdfGeneration(chartId) {
  return request(`/chart/${chartId}/pdf`, { method: 'POST' });
}

export async function getTaskStatus(taskId) {
  return request(`/tasks/${taskId}/status`);
}

export function pollTask(taskId, onProgress, intervalMs = 1500, timeoutMs = 120_000) {
  return new Promise((resolve, reject) => {
    const start = Date.now();

    const tick = async () => {
      if (Date.now() - start > timeoutMs) {
        return reject(new Error('Task timeout'));
      }

      try {
        const data = await getTaskStatus(taskId);
        onProgress?.({ status: data.status, step: data.step });

        if (data.status === 'success') return resolve(data.result);
        if (data.status === 'failure') return reject(new Error(data.error || 'Task failed'));

        setTimeout(tick, intervalMs);
      } catch (err) {
        reject(err);
      }
    };

    tick();
  });
}

// ── Lunar Calendar API ──

export async function getLunarCalendar(year, month) {
  const params = new URLSearchParams();
  if (year)  params.set('year', year);
  if (month) params.set('month', month);
  return request(`/calendar/lunar?${params}`);
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

export async function validatePromoCode(code) {
  // Пробуем создать сессию с промокодом — если invalid_promo_code, бросаем
  // Используем отдельный лёгкий эндпоинт-валидатор (или полагаемся на ошибку checkout)
  // Здесь делаем HEAD-запрос к специальному эндпоинту валидации
  const token = localStorage.getItem('astro_access_token');
  return request(`/payments/promo-validate?code=${encodeURIComponent(code)}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
}

export async function createReportCheckoutSession(reportType, chartId) {
  const token = localStorage.getItem('astro_access_token');
  return request('/payments/checkout/report', {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: JSON.stringify({ report_type: reportType, chart_id: chartId }),
  });
}
