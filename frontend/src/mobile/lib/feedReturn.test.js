import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { returnTarget, topVisibleDay } from './feedReturn';

const days = [{ date: '2026-08-27' }, { date: '2026-09-20' }, { date: '2026-09-27' }, { date: '2026-10-02' }];

describe('topVisibleDay', () => {
  it('день, ушедший за кромку, и насколько', () => {
    const tops = [{ date: 'a', top: -900 }, { date: 'b', top: -120 }, { date: 'c', top: 300 }];
    expect(topVisibleDay(tops, 0)).toEqual({ date: 'b', offset: 120 });
  });
  it('прокручено к самому верху — первый день с отрицательным отступом', () => {
    expect(topVisibleDay([{ date: 'a', top: 200 }], 0)).toEqual({ date: 'a', offset: -200 });
  });
  it('пусто — null', () => {
    expect(topVisibleDay([], 0)).toBeNull();
  });
});

describe('returnTarget', () => {
  it('первое открытие — на сегодня, не в начало окна', () => {
    expect(returnTarget(null, days, '2026-09-27')).toEqual({ date: '2026-09-27', offset: 0 });
  });
  it('возврат — на тот же день и отступ, где оставили', () => {
    expect(returnTarget({ date: '2026-09-20', offset: 57 }, days, '2026-09-27'))
      .toEqual({ date: '2026-09-20', offset: 57 });
  });
  it('день пропал из ленты — ближайший следующий', () => {
    expect(returnTarget({ date: '2026-09-25', offset: 40 }, days, '2026-09-27'))
      .toEqual({ date: '2026-09-27', offset: 0 });
  });
  it('следующих нет — последний', () => {
    expect(returnTarget({ date: '2026-12-01', offset: 0 }, days, '2026-09-27'))
      .toEqual({ date: '2026-10-02', offset: 0 });
  });
  it('лента пуста — null', () => {
    expect(returnTarget({ date: '2026-09-20', offset: 0 }, [], '2026-09-27')).toBeNull();
  });
});

// Рендер-тестов в проекте нет (ни jsdom, ни testing-library), поэтому связь
// с экраном закреплена по исходнику — как в feedAnchor.test.js.
describe('FeedScreen возвращается на сохранённый день', () => {
  const src = readFileSync(fileURLToPath(new URL('../screens/FeedScreen.jsx', import.meta.url)), 'utf-8');
  it('возврат на вкладку ведёт к returnTarget, а не оставляет сброшенный scrollTop', () => {
    expect(src).toMatch(/returnTarget\(savedPosRef\.current/);
  });
  it('позиция пишется на прокрутке через topVisibleDay', () => {
    expect(src).toMatch(/savedPosRef\.current = topVisibleDay\(/);
  });
  it('смена карты забывает позицию — лента откроется на сегодня', () => {
    const effect = src.slice(src.indexOf('seenChartsVersion.current = chartsVersion'));
    expect(effect.slice(0, 200)).toMatch(/savedPosRef\.current = null/);
  });
});
