import { describe, it, expect } from 'vitest';
import { buildUpcoming, formatWeekRange, railPositions } from './plannerDates';

describe('неделя планера — родительный падеж', () => {
  it('«28 сентября – 4 октября», в одном месяце — «5–11 октября»', () => {
    expect(formatWeekRange('2026-09-28', '2026-10-04')).toBe('28 сентября – 4 октября');
    expect(formatWeekRange('2026-10-05', '2026-10-11')).toBe('5–11 октября');
  });
});

describe('«Ближайшие 30 дней»', () => {
  const now = new Date(2026, 8, 29);
  const plan = {
    upcoming: [
      { date: '2026-10-03', kind: 'station', planet: 'venus', planet_name: 'Венера', status: 'start' },
      { date: '2026-10-16', kind: 'station', planet: 'pluto', planet_name: 'Плутон', status: 'end' },
      { date: '2026-10-22', kind: 'passage', planet: 'sun', planet_name: 'Солнце', house: 2, until: '2026-11-21' },
      { date: '2026-11-05', kind: 'passage', planet: 'mars', planet_name: 'Марс', house: 3, until: null },
    ],
  };
  const lunar = [
    { phases: [{ date: '2026-09-26', type: 'full_moon', sign: 'Овен', time: '19:49 GMT+3' }] },
    { phases: [{ date: '2026-10-26', type: 'full_moon', sign: 'Телец', time: '07:12 GMT+3' },
               { date: '2026-10-10', type: 'new_moon', sign: 'Весы', time: '03:50 GMT+3' }] },
    // тот же месяц пришёл второй раз — без дублей
    { phases: [{ date: '2026-10-26', type: 'full_moon', sign: 'Телец', time: '07:12 GMT+3' }] },
  ];
  const ev = buildUpcoming(plan, lunar, now);

  it('окно от сегодня на 30 дней, по дате, без дублей', () => {
    expect(ev.map((e) => e.date)).toEqual(['2026-10-03', '2026-10-10', '2026-10-16', '2026-10-22', '2026-10-26']);
  });

  it('подписи: фазы с заглавной, развороты «назад»/«вперёд», переход с датой выхода', () => {
    expect(ev.map((e) => e.short)).toEqual([
      'Венера разворачивается назад', 'Новолуние', 'Плутон разворачивается вперёд',
      'Солнце переходит в 2 дом', 'Полнолуние',
    ]);
    expect(ev[3].detail).toBe('Солнце входит в 2 дом и пробудет там до 21 ноября.');
    expect(ev[4].detail).toBe('Полнолуние в Тельце, 07:12 по Москве.');
  });

  it('рельс: узлы в пределах 0..1, соседи не ближе зазора', () => {
    const { pos, gap } = railPositions(['2026-10-03', '2026-10-03', '2026-10-04', '2026-10-29'], now);
    expect(pos[0]).toBeGreaterThanOrEqual(0);
    expect(pos[pos.length - 1]).toBeLessThanOrEqual(1);
    for (let i = 1; i < pos.length; i++) expect(pos[i] - pos[i - 1]).toBeGreaterThanOrEqual(gap - 1e-9);
  });
});
