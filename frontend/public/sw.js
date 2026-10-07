// ── Имена кэшей ──────────────────────────────────────────────────────────────
const CACHE_NAME   = 'astro-spa-v2';     // основной кэш статики
const CHARTS_CACHE = 'astro-charts-v1'; // сохранённые натальные карты (офлайн)

// Ресурсы для прекэша при установке
const PRECACHE_URLS = ['/', '/index.html'];

// ── INSTALL ───────────────────────────────────────────────────────────────────
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(PRECACHE_URLS))
  );
  self.skipWaiting();
});

// ── ACTIVATE — удаляем устаревшие кэши ───────────────────────────────────────
self.addEventListener('activate', (event) => {
  const KNOWN = [CACHE_NAME, CHARTS_CACHE];
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => !KNOWN.includes(k)).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// ── FETCH ─────────────────────────────────────────────────────────────────────
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Не-http(s) (chrome-extension:, data: и т. п.) — мимо воркера: Cache API
  // такие запросы не принимает, cache.put бросает TypeError.
  if (url.protocol !== 'http:' && url.protocol !== 'https:') return;

  // Кэшируем сохранённые карты в отдельный кэш
  if (request.method === 'GET' && /^\/api\/v1\/chart\/[^/]+$/.test(url.pathname)) {
    event.respondWith(networkFirstWithChartsCache(request));
    return;
  }

  // Network-first только для GET API (POST/PUT не кэшируем)
  if (url.pathname.startsWith('/api/')) {
    if (request.method !== 'GET') return; // пропускаем POST/PUT как есть
    event.respondWith(networkFirst(request));
    return;
  }

  // Cache-first для статики
  if (/\.(js|css|png|svg|ico|woff2?)(\?.*)?$/.test(url.pathname)) {
    event.respondWith(cacheFirst(request));
    return;
  }

  // Навигация — network-first + fallback на SPA shell
  if (request.mode === 'navigate') {
    event.respondWith(networkFirstWithFallback(request));
    return;
  }
});

// ── Стратегии ─────────────────────────────────────────────────────────────────

/** Network-first: пробуем сеть, при ошибке — кэш (только GET) */
async function networkFirst(request) {
  try {
    const res = await fetch(request);
    if (res.ok && request.method === 'GET') {
      const cache = await caches.open(CACHE_NAME);
      cache.put(request, res.clone());
    }
    return res;
  } catch {
    const cached = await caches.match(request);
    return cached ?? new Response('{}', { status: 503, headers: { 'Content-Type': 'application/json' } });
  }
}

/** Network-first для навигации + offline fallback на /index.html */
async function networkFirstWithFallback(request) {
  try {
    const res = await fetch(request);
    if (res.ok) {
      const cache = await caches.open(CACHE_NAME);
      cache.put(request, res.clone());
    }
    return res;
  } catch {
    const cached = await caches.match(request);
    if (cached) return cached;
    return caches.match('/index.html');
  }
}

/** Cache-first: кэш → сеть → кэшировать */
async function cacheFirst(request) {
  const cached = await caches.match(request);
  if (cached) return cached;
  try {
    const res = await fetch(request);
    if (res.ok) {
      const cache = await caches.open(CACHE_NAME);
      cache.put(request, res.clone());
    }
    return res;
  } catch {
    return new Response('Not found', { status: 404 });
  }
}

/** Network-first + сохраняем карту в CHARTS_CACHE для офлайн-просмотра */
async function networkFirstWithChartsCache(request) {
  try {
    const res = await fetch(request);
    if (res.ok) {
      const cache = await caches.open(CHARTS_CACHE);
      cache.put(request, res.clone());
    }
    return res;
  } catch {
    const cached = await caches.match(request, { cacheName: CHARTS_CACHE });
    return cached ?? new Response(
      JSON.stringify({ error: 'Офлайн — карта недоступна' }),
      { status: 503, headers: { 'Content-Type': 'application/json' } }
    );
  }
}

// ── PUSH NOTIFICATIONS ───────────────────────────────────────────────────────
// ⚠️ Уведомление показывается на КАЖДЫЙ пуш, даже пустой или битый. Safari
// (iPhone) и Chrome требуют показа на каждый push: молчаливый пуш Safari
// считает нарушением и после нескольких отзывает подписку. Поэтому никаких
// ранних return — нет данных, берём запасной текст (на «ты», без рода).
const PUSH_FALLBACK_TITLE = 'Aristea';
const PUSH_FALLBACK_BODY  = 'Загляни в Aristea — для тебя есть новое.';

self.addEventListener('push', (event) => {
  let payload = {};
  if (event.data) {
    try { payload = event.data.json() || {}; } catch { payload = { body: event.data.text() }; }
  }
  event.waitUntil(
    self.registration.showNotification(payload.title || PUSH_FALLBACK_TITLE, {
      body:    payload.body || PUSH_FALLBACK_BODY,
      icon:    '/icons/icon-192.png',
      badge:   '/icons/icon-192.png',
      vibrate: [200, 100, 200],
      data:    { url: payload.url || '/' },
    })
  );
});

// Клик по уведомлению — фокус на вкладку или открыть новую
self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const targetUrl = event.notification.data?.url ?? '/';
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((list) => {
      for (const client of list) {
        if (client.url === targetUrl && 'focus' in client) return client.focus();
      }
      return clients.openWindow(targetUrl);
    })
  );
});
