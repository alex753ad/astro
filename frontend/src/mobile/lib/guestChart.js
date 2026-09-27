/**
 * guestChart.js — карта гостя: построена до регистрации (решение владельца
 * 27.09.2026 — человек видит свою карту и прогноз до того, как его просят
 * зарегистрироваться).
 *
 * Сервер хранит такую карту как анонимную: `POST /chart/calculate` без входа
 * отдаёт `access_token` на 7 дней, лента и прогнозы открываются по заголовку
 * `X-Chart-Token`. После входа карта переходит на аккаунт той же строкой
 * (`POST /chart/{id}/claim`, backend/CLAUDE.md «Гость приложения») — это
 * делает ClaimGate в MobileApp.jsx, отсюда только хранение.
 *
 * ⚠️ localStorage, а не Preferences: гостевая карта нужна синхронно на первом
 * рендере (MobileRouter выбирает стартовый экран), а асинхронное чтение дало
 * бы кадр с экраном входа. Потеря записи (система вычистила хранилище) стоит
 * гостю одной формы — карта всё равно живёт 7 дней.
 */

const KEY = 'aristea_guest_chart';

/** @returns {{id: string, token: string, name?: string, expiresAt: string}|null} */
export function getGuestChart(now = Date.now()) {
  try {
    const g = JSON.parse(localStorage.getItem(KEY) || 'null');
    if (!g?.id || !g?.token) return null;
    // Просроченная карта на сервере уже закрыта (и будет удалена чисткой):
    // держать её здесь значило бы открыть ленту, которая ответит 404.
    if (g.expiresAt && Date.parse(g.expiresAt) <= now) {
      localStorage.removeItem(KEY);
      return null;
    }
    return g;
  } catch {
    return null;
  }
}

export function setGuestChart({ id, token, name, expiresAt }) {
  try {
    localStorage.setItem(KEY, JSON.stringify({ id, token, name: name || null, expiresAt }));
  } catch { /* без хранилища гость живёт до перезапуска — это его форма */ }
}

export function clearGuestChart() {
  try { localStorage.removeItem(KEY); } catch { /* нечего чистить */ }
}

/** Гость — есть гостевая карта и нет входа. */
export function isGuest() {
  let signedIn = false;
  try { signedIn = Boolean(localStorage.getItem('astro_access_token')); } catch { /* нет */ }
  return !signedIn && Boolean(getGuestChart());
}

/**
 * Заголовок токена карты — только к запросам про ЭТУ карту. Токен — ключ к
 * дате и месту рождения; слать его на чужие адреса (оплата, поддержка) незачем.
 */
export function guestHeaders(url) {
  const g = getGuestChart();
  if (!g || typeof url !== 'string' || !url.includes(`/chart/${g.id}`)) return {};
  return { 'X-Chart-Token': g.token };
}
