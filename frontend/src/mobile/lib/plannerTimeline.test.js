import { describe, it, expect } from 'vitest';
import { plannerTimeline } from './feedNow';
import { PLANNER_PLANET_ORDER } from './feedGlyphs';

/**
 * Полоса планет — все три горизонта планера одним рядом (решение владельца
 * 16.09.2026). Проверяется то, что ломалось молча: у значков разъезжалась
 * СЕМАНТИКА (у Солнца число означало дни, у Юпитера — дом) и ПОРЯДОК, потому
 * что рядов было два и каждый собирал их сам.
 */

// Момент, а не дата: полоса показывает дом, в котором планета СЕЙЧАС.
// 16.09.2026, 12:00 по поясу карты — между проходом Луны, кончившимся в
// 03:00, и следующим, начавшимся в 07:00.
const NOW = Date.parse('2026-09-16T12:00:00+03:00');

const ev = (kind, planet, house, at, ends_at) => ({
  key: `${kind}:${planet}:${house}`,
  kind, at, ends_at,
  meta: { planet, house, planet_name: planet },
});

const moon = (house, at, ends) => ev('planner_moon_house', 'moon', house, at, ends);
const period = (planet, house, at, ends) => ev('planner_period', planet, house, at, ends);
const longterm = (planet, house) => ev('planner_longterm', planet, house, '2012-11-17T00:00:00+03:00', '2032-03-23T00:00:00+03:00');

const FULL = [
  moon(3, '2026-09-16T07:00:00+03:00', '2026-09-18T19:00:00+03:00'),
  period('sun', 12, '2026-09-06T00:00:00+03:00', '2026-09-28T00:00:00+03:00'),
  period('mercury', 1, '2026-09-14T00:00:00+03:00', '2026-09-30T00:00:00+03:00'),
  period('venus', 2, '2026-09-09T00:00:00+03:00', '2026-10-26T00:00:00+03:00'),
  period('mars', 10, '2026-08-23T00:00:00+03:00', '2026-10-24T00:00:00+03:00'),
  longterm('jupiter', 11), longterm('saturn', 7), longterm('uranus', 9),
  longterm('neptune', 6), longterm('pluto', 4),
];

describe('plannerTimeline — отбор для полосы планет', () => {
  it('все три горизонта в одном ряду', () => {
    const items = plannerTimeline(FULL, NOW);
    expect(items).toHaveLength(10);
    const kinds = new Set(items.map((e) => e.kind));
    expect(kinds).toEqual(new Set(['planner_moon_house', 'planner_period', 'planner_longterm']));
  });

  it('порядок берётся из PLANNER_PLANET_ORDER, а не из порядка событий', () => {
    // Вход перемешан нарочно: до 16.09.2026 порядок задавала выборка, и у
    // двух видов полосы он был разный.
    const shuffled = [...FULL].reverse();
    const planets = plannerTimeline(shuffled, NOW).map((e) => e.meta.planet);
    expect(planets).toEqual(PLANNER_PLANET_ORDER);
  });

  it('у каждой записи есть ДОМ — одна семантика на весь ряд', () => {
    // ⚠️ Смысл проверки: в ряду не должно быть записи, у которой нечего
    // показать номером. Смешение «дни периода» и «дом» в одном ряду —
    // ровно тот дефект, который приёмка и поймала.
    for (const e of plannerTimeline(FULL, NOW)) {
      expect(typeof e.meta.house).toBe('number');
      expect(e.meta.house).toBeGreaterThanOrEqual(1);
      expect(e.meta.house).toBeLessThanOrEqual(12);
    }
  });

  it('берётся проход Луны, покрывающий СЕГОДНЯ, а не первый по списку', () => {
    // Проходов по домам полсотни на окно; без проверки «покрывает сегодня»
    // в полосу попал бы самый старый.
    const events = [
      moon(11, '2026-08-20T05:00:00+03:00', '2026-08-22T09:00:00+03:00'),
      moon(12, '2026-09-13T22:00:00+03:00', '2026-09-16T03:00:00+03:00'),
      moon(3, '2026-09-16T07:00:00+03:00', '2026-09-18T19:00:00+03:00'),
      moon(4, '2026-09-18T19:01:00+03:00', '2026-09-21T02:00:00+03:00'),
    ];
    const items = plannerTimeline(events, NOW);
    expect(items).toHaveLength(1);
    expect(items[0].meta.house).toBe(3);
  });

  it('месячный период берётся тоже текущий', () => {
    const events = [
      period('sun', 11, '2026-08-07T00:00:00+03:00', '2026-09-06T00:00:00+03:00'),
      period('sun', 12, '2026-09-06T00:00:00+03:00', '2026-09-28T00:00:00+03:00'),
    ];
    expect(plannerTimeline(events, NOW)[0].meta.house).toBe(12);
  });

  it('долгосрочный берётся БЕЗ проверки на «сейчас»', () => {
    // ⚠️ Проверка на покрытие к нему не применяется намеренно: период
    // выбирает сервер правилом «содержит сегодня», а его `at` лежит на годы
    // раньше окна (Плутон — 2012). Здесь это видно на периоде, ЗАВЕДОМО не
    // покрывающем момент, — он всё равно обязан попасть в полосу.
    const stale = { ...longterm('pluto', 4), ends_at: '2020-01-01T00:00:00+03:00' };
    expect(plannerTimeline([stale], NOW)).toHaveLength(1);
  });

  it('планета без записи в ряд не попадает', () => {
    // Пустой значок сообщал бы, что горизонт есть, а данных нет.
    const items = plannerTimeline([longterm('pluto', 4), moon(3, '2026-09-16T07:00:00+03:00', '2026-09-18T19:00:00+03:00')], NOW);
    expect(items.map((e) => e.meta.planet)).toEqual(['moon', 'pluto']);
  });

  it('транзиты и лунные события в полосу не попадают', () => {
    const noise = [
      { key: 't1', kind: 'transit', at: '2026-09-16T10:00:00+03:00', meta: { transit_planet: 'Moon' } },
      { key: 'm1', kind: 'moon_phase', at: '2026-09-16T10:00:00+03:00', meta: {} },
    ];
    expect(plannerTimeline(noise, NOW)).toHaveLength(0);
  });

  it('пустой вход не роняет правило', () => {
    expect(plannerTimeline([], NOW)).toEqual([]);
    expect(plannerTimeline(null, NOW)).toEqual([]);
  });
});
