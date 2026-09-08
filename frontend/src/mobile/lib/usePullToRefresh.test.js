/**
 * usePullToRefresh.test.js — решения жеста «потянуть, чтобы обновить».
 *
 * Проверяется то и только то, что в этом проекте вообще проверяемо:
 * DOM-окружения для тестов нет (ни jsdom, ни testing-library), touch-события
 * подделать нечем, и всё внутри эффекта остаётся на приёмку руками. Поэтому
 * решения о направлении и о высоте полоски вынесены чистыми функциями — по
 * образцу lib/refreshSchedule.js, где непроверяемость логики внутри хука
 * однажды уже стоила двух прожитых незамеченными дефектов.
 *
 * Главный кейс здесь — 'abandon' по горизонтали: на «Ленте» жест начинается
 * ровно поверх горизонтальной полоски дней (FeedDayStrip), и без этой
 * развилки прокрутка полоски и потягивание ленты спорили бы за один палец.
 */
import { describe, expect, it } from 'vitest';
import { PULL_THRESHOLD, gestureDecision, pullOffset } from './usePullToRefresh';

describe('gestureDecision — чей это палец', () => {
  it('вертикально вниз — тянем', () => {
    expect(gestureDecision(0, 40)).toBe('pull');
    expect(gestureDecision(6, 40)).toBe('pull'); // немного вбок — всё ещё вниз
  });

  it('горизонталь отдаём полоске дней, в обе стороны', () => {
    expect(gestureDecision(30, 10)).toBe('abandon');
    expect(gestureDecision(-30, 10)).toBe('abandon');
    // Ровно по диагонали — тоже не наш: полоска дней важнее ложного жеста.
    expect(gestureDecision(20, 20)).toBe('abandon');
  });

  it('вверх — это обычная прокрутка, а не жест', () => {
    expect(gestureDecision(0, -40)).toBe('abandon');
  });

  it('пока сдвиг мал — решение не принимается', () => {
    expect(gestureDecision(0, 3)).toBe('undecided');
    expect(gestureDecision(1, 7)).toBe('undecided');
  });
});

describe('pullOffset — насколько выросла полоска', () => {
  it('палец идёт вдвое быстрее полоски — иначе жест «липкий»', () => {
    expect(pullOffset(100)).toBe(50);
  });

  it('порог достижим и достигается не сразу', () => {
    expect(pullOffset(PULL_THRESHOLD)).toBeLessThan(PULL_THRESHOLD);
    expect(pullOffset(PULL_THRESHOLD * 2)).toBeGreaterThanOrEqual(PULL_THRESHOLD);
  });

  it('дальше упора полоска не растёт — жест не бездонный', () => {
    expect(pullOffset(10000)).toBe(pullOffset(1000));
  });

  it('обратный ход не даёт отрицательной высоты', () => {
    expect(pullOffset(-50)).toBe(0);
    expect(pullOffset(0)).toBe(0);
  });
});
