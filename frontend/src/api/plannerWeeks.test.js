import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { PLANNER_WEEKS_AHEAD } from "../constants";

/**
 * Синхронность недельного планера между витриной и тарифной сеткой.
 *
 * Построен по образцу `transitsHorizon.test.js` и по той же причине: число
 * живёт в двух местах и в разных языках —
 *
 *   - `rate_limits.py` — `TIER_FLAGS[*]["planner_weeks_ahead"]`, по которому
 *     сервер решает, отдавать ли расшифровку прохода Луны по дому
 *     (`is_moon_week_locked`);
 *   - `constants.js` — `PLANNER_WEEKS_AHEAD`, по которому набирается строка
 *     на /pricing и в модалках сравнения.
 *
 * Разойдутся — витрина пообещает недели, которых сервер не отдаст, и увидит
 * это только заплативший. Обе половины по отдельности останутся при этом
 * «правильными», то есть расхождение будет молчаливым.
 *
 * ⚠️ Отдельно проверяется, что у free число РОВНО единица. Это не
 * перестраховка: единица означает «только текущая неделя», и именно на ней
 * держится формулировка витрины. Подняв флаг до двух и не тронув текст, мы
 * получили бы тариф, отдающий больше обещанного, — дефект того же класса,
 * что письма про 5 PDF при `pdf_per_month = 15`.
 */

const repoRoot = fileURLToPath(new URL("../../../", import.meta.url));
const read = (p) => readFileSync(repoRoot + p, "utf-8");

const BACKEND = "backend/auth/rate_limits.py";
const FRONTEND = "frontend/src/constants.js";

/** TIER_FLAGS[tier]["planner_weeks_ahead"] из rate_limits.py. */
function backendWeeks(tier) {
  const src = read(BACKEND);
  const order = ["free", "lite", "pro", "premium"];
  const start = src.indexOf(`"${tier}": {`);
  expect(start, `в ${BACKEND} не найден тариф ${tier}`).toBeGreaterThan(-1);
  const nextTier = order[order.indexOf(tier) + 1];
  const end = nextTier ? src.indexOf(`"${nextTier}": {`) : src.length;
  const m = src.slice(start, end).match(/"planner_weeks_ahead":\s*(None|\d+)/);
  expect(m, `в ${BACKEND} не найден planner_weeks_ahead у ${tier}`).not.toBeNull();
  // `None` в TIER_FLAGS — это «всё окно», на фронте тем же смыслом `null`.
  return m[1] === 'None' ? null : Number(m[1]);
}

describe("недельный планер: витрина и тарифная сетка считают одинаково", () => {
  it.each(["free", "lite", "pro", "premium"])("%s", (tier) => {
    expect(PLANNER_WEEKS_AHEAD[tier]).toBe(backendWeeks(tier));
  });

  it("у free ровно одна неделя — на этом держится текст витрины", () => {
    expect(backendWeeks("free")).toBe(1);
  });

  it("у платных — всё окно, а не число недель", () => {
    // ⚠️ null/None, а не большое число. Конечное число означало бы состояние
    // «закрыто, и купить нечем»: у всех платных тарифов оно одинаково, то
    // есть апгрейд не открывал бы ничего. Это и отменено 16.09.2026.
    for (const tier of ["lite", "pro", "premium"]) {
      expect(backendWeeks(tier)).toBeNull();
      expect(PLANNER_WEEKS_AHEAD[tier]).toBeNull();
    }
  });

  it("витрина платных обещает весь горизонт, а не недели", () => {
    // Число из константы больше не подставляется — подставлять нечего.
    // Проверка держит то же самое: текст не разъезжается с флагом.
    const src = read(FRONTEND);
    expect(src).toContain("Луна по домам на весь горизонт ленты");
    expect(src).not.toContain("PLANNER_WEEKS_AHEAD.lite}");
  });

  it("витрина free называет и прошедшие периоды, а не только текущую неделю", () => {
    // Прошлое открыто всем мимо этого числа (is_moon_week_locked). Текст,
    // называющий одну текущую неделю, недодавал бы человеку то, что у него
    // уже есть, — и делал бы это незаметно.
    expect(read(FRONTEND)).toContain("текущая неделя и все прошедшие периоды");
  });
});
