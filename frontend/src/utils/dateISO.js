/**
 * ISO-дата (YYYY-MM-DD) арифметика — чисто в UTC-компонентах.
 *
 * "YYYY-MM-DDT00:00:00" без явного 'Z' парсится как ЛОКАЛЬНОЕ время, а
 * .toISOString() потом конвертирует в UTC — для часовых поясов восточнее UTC
 * (Europe/Moscow, UTC+3, основной пояс аудитории) локальная полночь уходит на
 * предыдущие сутки UTC. В цикле по датам (addDaysISO(d, 1) повторно) это была
 * неподвижная точка — d не менялся вообще, натуральный бесконечный цикл, не
 * просто "медленно" (регрессия перфоманса вкладки "Транзиты", коммит 78da87f).
 * Все функции здесь строят и меняют дату целиком в UTC — локальная таймзона
 * не участвует нигде.
 */

export function addDaysISO(dateStr, days) {
  const [y, m, d] = dateStr.split("-").map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d));
  dt.setUTCDate(dt.getUTCDate() + days);
  return dt.toISOString().slice(0, 10);
}

// Переполнение дня месяца (31 января + 1 месяц — в феврале нет 31-го) без
// явной обработки "перетекает" в следующий месяц (setUTCMonth(+1) от
// 2026-01-31 дал бы 2026-03-03). Якорим на 1-е число перед сдвигом месяца —
// день 1 существует в любом месяце, setUTCMonth не может переполниться — а
// целевой день прижимаем к последнему дню уже сдвинутого месяца.
function shiftMonthISO(dateStr, delta) {
  const [y, m, d] = dateStr.split("-").map(Number);
  const dt = new Date(Date.UTC(y, m - 1, 1));
  dt.setUTCMonth(dt.getUTCMonth() + delta);
  const lastDay = new Date(Date.UTC(dt.getUTCFullYear(), dt.getUTCMonth() + 1, 0)).getUTCDate();
  dt.setUTCDate(Math.min(d, lastDay));
  return dt.toISOString().slice(0, 10);
}

export function addMonthISO(dateStr) {
  return shiftMonthISO(dateStr, 1);
}

export function subMonthISO(dateStr) {
  return shiftMonthISO(dateStr, -1);
}
