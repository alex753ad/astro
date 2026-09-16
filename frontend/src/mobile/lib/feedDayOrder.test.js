import { describe, it, expect } from 'vitest';
import { splitDayEvents } from './feedDayOrder';

/**
 * Порядок внутри дня. Проверяется ровно то, что поймала приёмка 16.09.2026:
 * одиночное лунное событие уезжало в конец дня мимо своего времени.
 */

const at = (hhmm) => `2026-09-16T${hhmm}:00+03:00`;

const period = (hhmm, house = 3) => ({
  key: `p${hhmm}`, kind: 'planner_moon_house', importance: 'medium',
  at: at(hhmm), ends_at: at('23:59'), meta: { planet: 'moon', house },
});
const transit = (hhmm, low = false) => ({
  key: `t${hhmm}`, kind: 'transit', importance: low ? 'low' : 'medium',
  at: at(hhmm), meta: { transit_planet: low ? 'Moon' : 'Mercury', natal_planet: 'Saturn' },
});
const phase = (hhmm) => ({ key: `f${hhmm}`, kind: 'moon_phase', importance: 'medium', at: at(hhmm), meta: {} });

const times = (list) => list.map((e) => e.at.slice(11, 16));

describe('splitDayEvents — порядок событий внутри дня', () => {
  it('одиночное лунное встаёт ПО ВРЕМЕНИ, а не в конец дня', () => {
    // Ровно случай приёмки: «19:33 Луна в 3 доме», под ним «07:56 Луна — Сатурн».
    const day = { events: [transit('07:56', true), period('19:33')] };
    const { inFlow, folded } = splitDayEvents(day);
    expect(times(inFlow)).toEqual(['07:56', '19:33']);
    expect(folded).toEqual([]);
  });

  it('период, транзиты и лунные в одном дне — строго по времени', () => {
    const day = {
      events: [transit('03:11'), period('07:00'), phase('12:40'), transit('18:20', true), transit('21:05')],
    };
    const { inFlow, folded } = splitDayEvents(day);
    expect(times(inFlow)).toEqual(['03:11', '07:00', '12:40', '18:20', '21:05']);
    expect(folded).toEqual([]);
  });

  it('от двух лунных и больше — они уходят под свёртку, остальное по времени', () => {
    const day = {
      events: [transit('02:00', true), period('07:00'), transit('09:30', true), transit('21:05')],
    };
    const { inFlow, folded } = splitDayEvents(day);
    expect(times(inFlow)).toEqual(['07:00', '21:05']);
    expect(times(folded)).toEqual(['02:00', '09:30']);
  });

  it('свёртка сохраняет порядок событий внутри себя', () => {
    const day = { events: [transit('02:00', true), transit('09:30', true), transit('18:00', true)] };
    expect(times(splitDayEvents(day).folded)).toEqual(['02:00', '09:30', '18:00']);
  });

  it('⚠️ свой сортировки здесь нет — порядок берётся с сервера как есть', () => {
    // Если сервер по какой-то причине отдал не по возрастанию, клиент это НЕ
    // исправляет: вторая сортировка стала бы вторым источником правды о
    // порядке, и расхождение с сервером было бы не видно ниоткуда.
    const day = { events: [period('19:33'), transit('07:56', true)] };
    expect(times(splitDayEvents(day).inFlow)).toEqual(['19:33', '07:56']);
  });

  it('день без лунных не трогается', () => {
    const day = { events: [transit('03:11'), phase('12:40')] };
    const { inFlow, folded } = splitDayEvents(day);
    expect(inFlow).toHaveLength(2);
    expect(folded).toEqual([]);
  });

  it('пустой день не роняет правило', () => {
    expect(splitDayEvents({ events: [] })).toEqual({ inFlow: [], folded: [] });
    expect(splitDayEvents(null)).toEqual({ inFlow: [], folded: [] });
  });
});
