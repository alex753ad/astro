/**
 * paySheetBus.js — «открыть оплату» из любого места приложения.
 *
 * Кнопок, ведущих к оплате, девять в пяти компонентах (пейволлы ленты,
 * разбора, чата, создания карты, блок тарифа). Лист оплаты один и живёт в
 * TabShell; кнопки только просят его открыться. Раньше каждая открывала
 * веб-страницу тарифов сама — одна дверь к оплате лучше девяти.
 */

const listeners = new Set();

/** @param {{mode?: 'choose'|'status'}} [opts] */
export function openPaySheet(opts = {}) {
  for (const fn of [...listeners]) fn({ mode: 'choose', ...opts });
}

export function onPaySheet(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}
