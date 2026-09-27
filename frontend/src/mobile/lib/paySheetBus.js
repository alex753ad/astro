/**
 * paySheetBus.js — «открыть оплату» из любого места приложения.
 *
 * Кнопок, ведущих к оплате, девять в пяти компонентах (пейволлы ленты,
 * разбора, чата, создания карты, блок тарифа). Лист оплаты один и живёт в
 * TabShell; кнопки только просят его открыться. Раньше каждая открывала
 * веб-страницу тарифов сама — одна дверь к оплате лучше девяти.
 */

const listeners = new Set();

/**
 * @param {{mode?: 'choose'|'status', focus?: string, alt?: string|null,
 *          context?: string, returnTo?: object}} [opts]
 * `focus`/`alt` — какой тариф предложить (lib/offerRule.js), `context` —
 * строка «что откроется», `returnTo` — куда вернуться после оплаты
 * (lib/afterPay.js). Без них — все продаваемые старше текущего.
 *
 * ⚠️ Звать только по нажатию человека на закрытое (решение владельца
 * 27.09.2026): листов с предложением, открывающихся сами, нет.
 */
export function openPaySheet(opts = {}) {
  for (const fn of [...listeners]) fn({ mode: 'choose', ...opts });
}

export function onPaySheet(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}
