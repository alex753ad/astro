/**
 * feedRank.test.js — что остаётся карточкой в сжатом дне.
 *
 * Проверяется правило, а не вид: цена ошибки здесь — спрятанное событие, и
 * заметить его на устройстве нельзя (пропажу не видно, видно только то, что
 * есть). Отдельно закреплён случай, ради которого правило и писалось:
 * открытый разбор транзита не сжимается НИКОГДА — на free таких событий два
 * на весь горизонт.
 */

import { describe, expect, it } from 'vitest';
import { EXACT_ORB_DEG, isMajorEvent } from './feedRank';

const transit = (meta, extra = {}) => ({
  key: 't:1',
  kind: 'transit',
  importance: 'medium',
  at: '2026-09-15T18:27:00+03:00',
  teaser: { intro: 'закрыто', outro: 'на Веге' },
  meta: { transit_planet: 'Mercury', natal_planet: 'Uranus', aspect_type: 'square', ...meta },
  ...extra,
});

describe('isMajorEvent', () => {
  it('фаза, затмение, станция, равноденствие и период планера — всегда карточка', () => {
    for (const kind of ['moon_phase', 'eclipse', 'retrograde', 'solar_event', 'planner_period']) {
      expect(isMajorEvent({ kind, importance: 'medium', meta: {} })).toBe(true);
    }
  });

  it('открытый разбор транзита не сжимается — ни при каком орбе', () => {
    // teaser отсутствует = бэкенд открыл событие (см. isLocked в FeedEventCard).
    const open = transit({ peak_orb: 4.2, applying: false }, { teaser: null });
    expect(isMajorEvent(open)).toBe(true);
  });

  it('закрытый транзит с точным сходящимся аспектом — карточка', () => {
    expect(isMajorEvent(transit({ peak_orb: 0.036, applying: true }))).toBe(true);
  });

  it('тот же орб, но аспект расходится — рядовое', () => {
    expect(isMajorEvent(transit({ peak_orb: 0.036, applying: false }))).toBe(false);
  });

  it('сходящийся, но не точный — рядовое', () => {
    expect(isMajorEvent(transit({ peak_orb: 0.09, applying: true }))).toBe(false);
  });

  it('порог берётся строго: ровно EXACT_ORB_DEG — уже не точный', () => {
    expect(isMajorEvent(transit({ peak_orb: EXACT_ORB_DEG, applying: true }))).toBe(false);
  });

  it('лунный фон карточкой не становится даже при нулевом орбе', () => {
    const lunar = transit({ peak_orb: 0.001, applying: true }, { importance: 'low' });
    expect(isMajorEvent(lunar)).toBe(false);
  });

  // ⚠️ Проход Луны по дому с 16.09.2026 больше НЕ лунный фон: он вышел
  // из-под свёртки (FeedLunarFold.jsx) и стоит в потоке отдельной строкой.
  // Крупным он при этом не становится — их ~53 на окне ленты (замер
  // 16.09.2026), и карточка на каждый вернула бы ту самую массу, ради разбора
  // которой ритм и принят. Важность у него `medium`, а не `low`, — фикстура
  // повторяет то, что реально отдаёт сервер, иначе проверка была бы зелёной
  // по чужой причине.
  it('проход Луны по дому — строка, а не карточка', () => {
    expect(isMajorEvent({ kind: 'planner_moon_house', importance: 'medium', locked: true, meta: {} })).toBe(false);
    expect(isMajorEvent({ kind: 'planner_moon_house', importance: 'medium', locked: false, meta: {} })).toBe(false);
  });

  it('пустое значение не роняет правило', () => {
    expect(isMajorEvent(null)).toBe(false);
    expect(isMajorEvent(undefined)).toBe(false);
  });

  it('в боевом дне остаётся хотя бы одно рядовое событие — иначе ступени нет', () => {
    // Замер 15.09.2026, по которому выбран порог: при 0.1° крупными
    // становились пять транзитов из семи за неделю. Этот кейс держит сам
    // смысл ступени — правило обязано кого-то оставлять внизу.
    const day = [
      transit({ peak_orb: 0.036, applying: true }),
      transit({ peak_orb: 0.0718, applying: true }),
      transit({ peak_orb: 0.0938, applying: true }),
    ];
    const major = day.filter(isMajorEvent);
    expect(major).toHaveLength(1);
    expect(day.length - major.length).toBeGreaterThan(0);
  });
});
