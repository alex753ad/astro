/**
 * API client for Astro SPA backend.
 * 
 * Handles:
 * - REST calls (chart, transits)
 * - SSE streaming (AI interpretations)
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
          if (data === '[DONE]') {
            onDone?.();
            return;
          }
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

function _connectSSE(url, onChunk, onDone, onError) {
  const eventSource = new EventSource(url);
  let hasData = false;
  let isDone = false;

  eventSource.onmessage = (event) => {
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
    if (isDone || hasData) {
      onDone?.();
    } else {
      onError?.('Connection lost');
    }
  };

  return () => eventSource.close();
}

export { ApiError };
