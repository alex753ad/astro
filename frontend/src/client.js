/**
 * API client for Astro SPA backend.
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
  const resp = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });

  if (!resp.ok) {
    const body = await resp.json().catch(() => ({ detail: resp.statusText }));
    throw new ApiError(
      body.detail || resp.statusText,
      resp.status,
      body,
    );
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

function _connectSSE(url, onChunk, onDone, onError) {
  let lastEventId = null;
  let hasData     = false;
  let isDone      = false;
  let attempt     = 0;
  let eventSource = null;
  let retryTimeout = null;
  const maxRetries = 3;

  function connect() {
    const connectUrl = lastEventId
      ? url + (url.includes('?') ? '&' : '?') + 'last_event_id=' + encodeURIComponent(lastEventId)
      : url;

    eventSource = new EventSource(connectUrl);

    eventSource.onmessage = (event) => {
      if (event.lastEventId) lastEventId = event.lastEventId;

      if (event.data === '[DONE]') {
        isDone = true;
        eventSource.close();
        onDone?.();
        return;
      }
      try {
        const parsed = JSON.parse(event.data);
        if (parsed.text) {
          hasData = true;
          onChunk(parsed.text);
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
        // Если данные уже получены — считаем done, иначе — error
        if (hasData) { onDone?.(); } else { onError?.('Connection lost'); }
      }
    };
  }

  connect();

  return () => {
    clearTimeout(retryTimeout);
    eventSource?.close();
  };
}

export function streamInterpretation(chartId, onChunk, onDone, onError) {
  const url = `${API_BASE}/chart/${chartId}/interpret`;
  return _connectSSE(url, onChunk, onDone, onError);
}

export function streamTransitInterpretation(chartId, fromDate, toDate, onChunk, onDone, onError) {
  const params = new URLSearchParams({ from_date: fromDate, to_date: toDate });
  const url = `${API_BASE}/chart/${chartId}/transits/interpret?${params}`;
  return _connectSSE(url, onChunk, onDone, onError);
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

/**
 * Запустить асинхронный расчёт транзитов.
 * Возвращает { task_id, status }.
 */
export async function startTransitsAsync(chartId, fromDate, toDate, options = {}) {
  const params = new URLSearchParams({ from_date: fromDate, to_date: toDate });
  if (options.planet) params.set('planet', options.planet);
  if (options.maxOrb) params.set('max_orb', options.maxOrb);
  return request(`/chart/${chartId}/transits/async?${params}`, { method: 'POST' });
}

/**
 * Запустить асинхронную генерацию PDF.
 * Возвращает { task_id, status }.
 */
export async function startPdfGeneration(chartId) {
  return request(`/chart/${chartId}/pdf`, { method: 'POST' });
}

/**
 * Поллинг статуса задачи.
 * Возвращает { status, step?, result?, error? }.
 */
export async function getTaskStatus(taskId) {
  return request(`/tasks/${taskId}/status`);
}

/**
 * Поллинг до завершения задачи.
 *
 * @param {string} taskId
 * @param {function} onProgress — вызывается при каждом poll с { status, step }
 * @param {number} intervalMs — интервал поллинга (по умолчанию 1500ms)
 * @param {number} timeoutMs — таймаут (по умолчанию 120000ms)
 * @returns {Promise<any>} — result задачи при успехе
 */
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

        // pending | started — продолжаем поллить
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

export async function createCheckoutSession(tier, billing, chartId) {
  const token = localStorage.getItem('astro_access_token');
  return request('/payments/checkout', {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: JSON.stringify({ tier, billing, chart_id: chartId }),
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
