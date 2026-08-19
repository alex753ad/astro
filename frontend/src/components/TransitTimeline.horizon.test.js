import { describe, it, expect } from "vitest";
import { addDaysISO, addMonthISO, monthEndISO } from "../utils/dateISO";

/**
 * Чистая симуляция горизонта догрузки из TransitTimeline.jsx (initial fetch +
 * loadMore), без React/fetch — специально под узкие горизонты (Lite 1 мес,
 * Pro 3 мес, 19.08.2026: было 2 мес на оба тарифа плоско), которые раньше
 * никогда не тестировались и не наступали в реальном использовании (горизонт
 * всегда был ощутимо больше одного шага догрузки).
 *
 * Воспроизводит формулы 1:1 из TransitTimeline.jsx:
 *   - первый fetch: to = min(addMonthISO(today), horizonEnd)
 *   - loadMore:     to = min(addMonthISO(addDaysISO(to, 1)), horizonEnd)
 *   - reachedEnd, когда to >= horizonEnd
 */
function simulateHorizon(today, maxMonths, maxSteps = 30) {
  const horizonEnd = monthEndISO(today, maxMonths);
  const seenTo = [];

  let to = addMonthISO(today) > horizonEnd ? horizonEnd : addMonthISO(today);
  seenTo.push(to);
  let reachedEnd = to >= horizonEnd;
  let steps = 1;

  while (!reachedEnd) {
    if (steps > maxSteps) {
      throw new Error(`не сошлось за ${maxSteps} шагов (today=${today}, maxMonths=${maxMonths}) — возможен бесконечный цикл`);
    }
    const from = addDaysISO(to, 1);
    const next = addMonthISO(from) > horizonEnd ? horizonEnd : addMonthISO(from);
    if (next <= to) {
      throw new Error(`loadMore не продвигает границу (from ${to} к ${next}) — кнопка "›" зависла бы`);
    }
    to = next;
    seenTo.push(to);
    reachedEnd = to >= horizonEnd;
    steps++;
  }

  return { horizonEnd, seenTo, steps };
}

describe("TransitTimeline: горизонт догрузки не переваливает за тарифный лимит", () => {
  // Разные "сегодня": начало/конец месяца, конец года, високосный февраль —
  // именно тут чаще всего вылезают off-by-one в месячной арифметике.
  const sampleDates = [
    "2026-01-01", "2026-01-31", "2026-02-01", "2026-02-28",
    "2024-02-29", // високосный год
    "2026-08-19", "2026-12-01", "2026-12-31",
  ];

  // 1 — Lite, 3 — Pro (19.08.2026), 24 — Premium. 12 (Free) не тестируется
  // здесь: это не тарифный лимит транзитов, а отдельная величина для
  // блюр-тизера (см. комментарий в TransitTimeline.jsx), free до транзитов
  // не допускается вовсе (check_transit_access).
  for (const today of sampleDates) {
    for (const maxMonths of [1, 3, 24]) {
      it(`today=${today} maxMonths=${maxMonths} — доходит до горизонта и не переваливает`, () => {
        const { horizonEnd, seenTo, steps } = simulateHorizon(today, maxMonths);

        // Ни один промежуточный to не должен быть за горизонтом.
        for (const to of seenTo) {
          expect(to <= horizonEnd).toBe(true);
        }
        // Последний to обязан СОВПАСТЬ с горизонтом (не проскочить мимо).
        expect(seenTo[seenTo.length - 1]).toBe(horizonEnd);
        expect(steps).toBeGreaterThan(0);
      });
    }
  }

  it("узкий горизонт (1 мес) сходится не медленнее широкого (24 мес) — не более 2 шагов", () => {
    const { steps } = simulateHorizon("2026-08-19", 1);
    expect(steps).toBeLessThanOrEqual(2);
  });
});
