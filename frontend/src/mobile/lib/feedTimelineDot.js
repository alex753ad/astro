/**
 * feedTimelineDot.js — цвет и размер точки события на линии времени (§2
 * SPEC_FEED_VISUAL.md, «Заход А» — структура, не содержимое карточек).
 *
 * Точка одна на карточку в потоке (FeedScreen группирует их построчно),
 * поэтому цвет и размер решаются здесь по `kind`/`importance`, а не внутри
 * FeedEventCard — карточка в этом заходе не меняется вовсе.
 */

/**
 * Цвет планеты (§5, таблица) — общий для точки на линии (этот файл) и
 * цветной полосы карточки периода (`FeedEventCard.jsx`, §5 «заход Б»).
 * Один экспорт на оба места, чтобы не завести две копии одной таблицы.
 *
 * На практике из этой таблицы в потоке ленты видны только «быстрые»
 * планеты (`kind: planner_period`) — Солнце, Меркурий, Венера, Марс:
 * `planner_longterm` (Юпитер и медленнее) изъят из потока целиком
 * (FeedScreen.jsx, комментарий в шапке), а `planner_moon_house` попадает
 * под свёртку §7 (importance: low) и своей точки на линии не получает.
 * Ветка default остаётся на случай, если это когда-нибудь изменится —
 * не как недостающий кейс, а как осознанный запасной вариант.
 */
export function planetDotColor(planetKey) {
  const key = String(planetKey || '').toLowerCase();
  return PLANET_COLOR_KEYS.includes(key) ? `var(--planet-${key})` : 'var(--text-secondary)';
}

/**
 * Планеты, у которых есть свой токен цвета (`--planet-*`, mobile.css).
 *
 * ⚠️ До 16.09.2026 здесь стояли СЕМАНТИЧЕСКИЕ токены: Солнце брало
 * `--color-warning`, Меркурий `--color-air`, а «Сатурн и медленнее» — один
 * общий `--color-earth`. Значит пять медленных планет были одного цвета, то
 * есть цвет не различал их вовсе, а Венера красилась акцентом приложения и
 * менялась бы вместе с ним при редизайне. Теперь у каждой планеты свой тон,
 * общий с веб-планером, и подогнанный по контрасту в каждой теме — разбор в
 * mobile.css над `--planet-sun`.
 */
const PLANET_COLOR_KEYS = [
  'sun', 'moon', 'mercury', 'venus', 'mars',
  'jupiter', 'saturn', 'uranus', 'neptune', 'pluto',
];

/** Лунное событие — фаза или затмение, у обоих одинаковый цвет и размер. */
function isLunarEvent(event) {
  return event.kind === 'moon_phase' || event.kind === 'eclipse';
}

export function dotColor(event) {
  const meta = event.meta || {};
  switch (event.kind) {
    case 'transit': return 'var(--text-secondary)';
    case 'retrograde': return 'var(--color-danger)';
    case 'solar_event': return 'var(--accent-glow)';
    case 'planner_period':
    case 'planner_moon_house':
      return planetDotColor(meta.planet);
    default:
      return isLunarEvent(event) ? 'var(--color-warning)' : 'var(--text-secondary)';
  }
}

/** 13 px — важные и лунные события; 9 px — все остальные. */
export function dotSize(event) {
  return (event.importance === 'high' || isLunarEvent(event)) ? 13 : 9;
}
