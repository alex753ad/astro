/**
 * feedTimelineDot.js — цвет и размер точки события на линии времени (§2
 * SPEC_FEED_VISUAL.md, «Заход А» — структура, не содержимое карточек).
 *
 * Точка одна на карточку в потоке (FeedScreen группирует их построчно),
 * поэтому цвет и размер решаются здесь по `kind`/`importance`, а не внутри
 * FeedEventCard — карточка в этом заходе не меняется вовсе.
 */

/**
 * Цвет планеты для точки планерного периода (§5, таблица).
 *
 * На практике из этой таблицы в потоке ленты видны только «быстрые»
 * планеты (`kind: planner_period`) — Солнце, Меркурий, Венера, Марс:
 * `planner_longterm` (Юпитер и медленнее) изъят из потока целиком
 * (FeedScreen.jsx, комментарий в шапке), а `planner_moon_house` попадает
 * под свёртку §7 (importance: low) и своей точки на линии не получает.
 * Ветка default остаётся на случай, если это когда-нибудь изменится —
 * не как недостающий кейс, а как осознанный запасной вариант.
 */
function planetDotColor(planetKey) {
  switch (planetKey) {
    case 'sun': return 'var(--color-warning)';
    case 'mercury': return 'var(--color-air)';
    case 'venus': return 'var(--accent-glow)';
    case 'mars': return 'var(--color-danger)';
    case 'moon': return 'var(--text-secondary)';
    default: return 'var(--color-earth)'; // Сатурн и медленнее
  }
}

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
