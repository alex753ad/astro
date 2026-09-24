/**
 * utcOffset.js — смещение от UTC для места рождения: подпись и список выбора.
 *
 * Общий файл веба и приложения. Сервер отдаёт у карты `utc_offset_minutes`
 * (по какому смещению она ФАКТИЧЕСКИ построена) и `utc_offset_source`
 * ("place" — по поясу места с историей поясов, "manual" — задано человеком),
 * а принимает ручное значение в `utc_offset_minutes` запроса расчёта.
 */

/** 180 → «UTC+3», 330 → «UTC+5:30», −240 → «UTC−4». */
export function formatUtcOffset(minutes) {
  if (typeof minutes !== 'number' || !Number.isFinite(minutes)) return '';
  const sign = minutes >= 0 ? '+' : '−';
  const abs = Math.abs(minutes);
  const h = Math.floor(abs / 60);
  const m = abs % 60;
  return `UTC${sign}${h}${m ? `:${String(m).padStart(2, '0')}` : ''}`;
}

/** «UTC+3, по месту рождения» / «UTC+3, указано вручную»; пустая строка — нечего показать. */
export function utcOffsetLabel(chart) {
  const text = formatUtcOffset(chart?.utc_offset_minutes);
  if (!text) return '';
  return `${text}, ${chart.utc_offset_source === 'manual' ? 'указано вручную' : 'по месту рождения'}`;
}

/**
 * Варианты ручного выбора: все целые часы от −12 до +14 и реально
 * существовавшие дробные смещения. Пределы совпадают с проверкой сервера
 * (`BirthDataInput.utc_offset_minutes`, ge=-720, le=840).
 */
const FRACTIONAL = [-570, -210, 210, 270, 330, 345, 390, 525, 570, 630, 765];
export const UTC_OFFSET_CHOICES = [
  ...Array.from({ length: 27 }, (_, i) => (i - 12) * 60),
  ...FRACTIONAL,
].sort((a, b) => a - b);

/**
 * Ответ 400 `ambiguous_time` → варианты выбора с подписью и смещением.
 * Сервер шлёт `offsets` парой к `options`: сначала летнее, потом зимнее.
 * Без `offsets` (старый сервер) выбирать нечем — пустой список.
 */
export function ambiguousChoices(detail) {
  const offsets = Array.isArray(detail?.offsets) ? detail.offsets : [];
  const seasons = ['летнее', 'зимнее'];
  return offsets.map((offset, i) => ({
    offset,
    label: `${seasons[i] ?? ''} (${formatUtcOffset(offset)})`.trim(),
  }));
}
