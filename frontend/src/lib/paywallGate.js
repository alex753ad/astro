/**
 * paywallGate.js — E4: правила частоты активного пейволла.
 *
 * Пассивный блюр-витрина (E1/E2) — всегда, без ограничений.
 * Активная модалка апгрейда:
 *   - максимум 1 показ за сессию (sessionStorage);
 *   - после отказа («Продолжить бесплатно» / закрытие) — cooldown 3 дня (localStorage);
 *   - явное намерение (страница тарифов, «Хочу Pro») лимит обходит (forced).
 */

const SESSION_KEY  = 'paywall_shown_session';
const COOLDOWN_KEY = 'paywall_cooldown_until';
const COOLDOWN_MS  = 3 * 24 * 60 * 60 * 1000; // 3 дня

export function canShowPaywall() {
  try {
    if (sessionStorage.getItem(SESSION_KEY)) return false;
    const until = Number(localStorage.getItem(COOLDOWN_KEY) || 0);
    if (until && Date.now() < until) return false;
  } catch { /* storage недоступен — не блокируем */ }
  return true;
}

export function markPaywallShown() {
  try { sessionStorage.setItem(SESSION_KEY, '1'); } catch {}
}

export function markPaywallDismissed() {
  try { localStorage.setItem(COOLDOWN_KEY, String(Date.now() + COOLDOWN_MS)); } catch {}
}
