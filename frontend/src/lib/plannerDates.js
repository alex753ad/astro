/**
 * Даты и «Ближайшие 30 дней» веб-планера (PlannerPage.jsx). Вынесено из
 * страницы 29.09.2026, чтобы покрыть тестами: падежи месяцев и сборку
 * событий страница проверить не даёт.
 */

// Родительный падеж: «28 сентября». toLocaleString('ru-RU', { month: 'long' })
// без числа отдаёт именительный («сентябрь») — так неделя и читалась
// «28 сентябрь – 4 октябрь» (приёмка 29.09.2026).
export const MONTHS_GEN = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля',
  'августа', 'сентября', 'октября', 'ноября', 'декабря'];
const MONTHS_SHORT = ['янв', 'фев', 'мар', 'апр', 'мая', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'];

/** «2026-09-28», «2026-10-04» → «28 сентября – 4 октября»; один месяц — «5–11 октября». */
export function formatWeekRange(startIso, endIso) {
  if (!startIso || !endIso) return '';
  const [, sm, sd] = startIso.split('-').map(Number);
  const [, em, ed] = endIso.split('-').map(Number);
  return sm === em
    ? `${sd}–${ed} ${MONTHS_GEN[em - 1]}`
    : `${sd} ${MONTHS_GEN[sm - 1]} – ${ed} ${MONTHS_GEN[em - 1]}`;
}

// «23.09 — 01.12» → «23 сентября — 1 декабря», «02.07.2026» → «2 июля 2026».
// Сервер отдаёт даты периода строкой в числовом виде (house_passages
// _fmt_period), и эту же строку получает промпт планера — поэтому формат
// меняется только при показе, а не в источнике (решение владельца 29.09.2026).
export function datesInWords(text) {
  return String(text || '').replace(/\b(\d{2})\.(\d{2})(?:\.(\d{4}))?\b/g, (m, d, mo, y) => {
    const name = MONTHS_GEN[Number(mo) - 1];
    if (!name) return m;
    return `${Number(d)} ${name}${y ? ` ${y}` : ''}`;
  });
}

export const isoDay = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
export const shortDate = (iso) => `${Number(iso.slice(8, 10))} ${MONTHS_SHORT[Number(iso.slice(5, 7)) - 1]}`;
const isoWords = (iso) => `${Number(iso.slice(8, 10))} ${MONTHS_GEN[Number(iso.slice(5, 7)) - 1]}`;

// Знак в предложный падеж («в Раке», «в Водолее»)
const SIGN_PREP = {
  'Овен': 'Овне', 'Телец': 'Тельце', 'Близнецы': 'Близнецах', 'Рак': 'Раке',
  'Лев': 'Льве', 'Дева': 'Деве', 'Весы': 'Весах', 'Скорпион': 'Скорпионе',
  'Стрелец': 'Стрельце', 'Козерог': 'Козероге', 'Водолей': 'Водолее', 'Рыбы': 'Рыбах',
};

export const UPCOMING_DAYS = 30;   // = house_passages.UPCOMING_DAYS

/**
 * «Ближайшие 30 дней» (решение владельца 29.09.2026 вместо «Транзитного
 * таймлайна»): окно от сегодня, а не отображаемый месяц. Прежний рельс в
 * текущем месяце почти всегда пустовал — прошедшие периоды скрыты
 * (hide_fully_past), у планеты оставался один период и переходов не было.
 * Одинаково на всех тарифах; меньше двух событий блок не показывает
 * (решает страница).
 *
 * planData.upcoming — переходы и развороты (house_passages.compute_upcoming);
 * lunar — ответы /calendar/lunar за этот и следующий месяц (фазы, затмения).
 * short — подпись «с заглавной», её страница ставит после даты:
 * «26 окт · Полнолуние».
 */
export function buildUpcoming(planData, lunar, now = new Date()) {
  const from = isoDay(now);
  const to = isoDay(new Date(now.getFullYear(), now.getMonth(), now.getDate() + UPCOMING_DAYS));
  const events = [];

  (planData?.upcoming || []).forEach((e, i) => {
    const planet = e.planet_name;
    if (e.kind === 'passage') {
      events.push({
        id: `up-${i}`, date: e.date, dot: { type: e.planet }, planet: e.planet,
        short: `${planet} переходит в ${e.house} дом`,
        detail: `${planet} входит в ${e.house} дом${e.until ? ` и пробудет там до ${isoWords(e.until)}` : ''}.`,
      });
    } else {
      const retro = e.status === 'start';
      events.push({
        id: `up-${i}`, date: e.date, dot: { type: e.planet, retro }, planet: e.planet,
        short: `${planet} разворачивается ${retro ? 'назад' : 'вперёд'}`,
        detail: retro
          ? `${planet} останавливается и начинает попятное движение — ретроградность.`
          : `${planet} заканчивает ретроградность и снова идёт вперёд.`,
      });
    }
  });

  // Два месяца могут вернуть одно и то же событие — ключ по дате и виду.
  const seen = new Set();
  const once = (key) => (seen.has(key) ? false : (seen.add(key), true));
  (lunar || []).forEach((m) => {
    (m.phases || []).forEach((ph) => {
      if (!once(`${ph.type}-${ph.date}`)) return;
      const label = ph.type === 'full_moon' ? 'Полнолуние' : 'Новолуние';
      events.push({
        id: `ph-${ph.date}`, date: ph.date, dot: { type: ph.type },
        short: label,
        detail: `${label}${ph.sign ? ` в ${SIGN_PREP[ph.sign] || ph.sign}` : ''}, ${(ph.time || '').slice(0, 5)} по Москве.`,
      });
    });
    (m.eclipses || []).forEach((ec) => {
      if (!once(`${ec.type}-${ec.date}`)) return;
      const label = ec.type === 'solar' ? 'Солнечное затмение' : 'Лунное затмение';
      events.push({
        id: `ec-${ec.date}`, date: ec.date, dot: { type: ec.type === 'solar' ? 'solar_eclipse' : 'lunar_eclipse' },
        short: label,
        detail: `${label}, ${(ec.time || '').slice(0, 5)} по Москве.`,
      });
    });
  });

  return events
    .filter((e) => e.date >= from && e.date <= to)
    .sort((a, b) => a.date.localeCompare(b.date));
}

/**
 * Позиции узлов рельса по дате, доли 0..1 от окна «сегодня … +30 дней».
 * Соседей раздвигаем до gap — иначе узлы слипаются; страница задаёт рельсу
 * минимальную ширину под этот зазор, и на телефоне рельс прокручивается, а
 * не обрезается (приёмка 29.09.2026: на 390 px пропадал правый узел).
 */
export function railPositions(dates, now = new Date(), gap = 0.12) {
  const t0 = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const g = dates.length > 1 ? Math.min(gap, 1 / (dates.length - 1)) : gap;
  const pos = dates.map((iso) => {
    const [y, m, d] = iso.split('-').map(Number);
    return Math.min(1, Math.max(0, (new Date(y, m - 1, d).getTime() - t0) / (UPCOMING_DAYS * 864e5)));
  });
  for (let i = 1; i < pos.length; i++) pos[i] = Math.max(pos[i], pos[i - 1] + g);
  if (pos.length && pos[pos.length - 1] > 1) pos[pos.length - 1] = 1;
  for (let i = pos.length - 2; i >= 0; i--) pos[i] = Math.min(pos[i], pos[i + 1] - g);
  if (pos.length && pos[0] < 0) pos[0] = 0;
  return { pos, gap: g };
}
