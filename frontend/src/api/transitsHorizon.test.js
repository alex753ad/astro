import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

/**
 * Синхронность витрины транзитов для free между фронтендом и бэкендом.
 *
 * Зачем этот тест существует. Горизонт списка транзитов у free — это НЕ
 * тарифный флаг: `TIER_FLAGS["free"]["transits_months"] = 0`, и ноль там про
 * AI-разбор, а не про длину списка (решение E2 — список виден всем, платят за
 * разбор). Реальная величина витрины живёт в двух местах:
 *
 *   - `TransitTimeline.jsx` — литерал в `const maxMonths = isFree ? 12 : ...`,
 *     он и определяет, до какой даты фронтенд запрашивает транзиты;
 *   - `rate_limits.py` — `FREE_TRANSITS_TEASER_MONTHS`, по которому сервер с
 *     31.08.2026 отдаёт 403 за горизонтом.
 *
 * Два числа, обязанные совпадать, в разных языках и без общего источника —
 * ровно та конструкция, которая уже расходилась в этом проекте (копии
 * тарифной сетки, `charts_per_month` против `profiles_limit`). Разойдутся
 * здесь — free начнёт получать 403 прямо на витрине, то есть сломается
 * страница, на которой строится весь апселл, и произойдёт это молча: обе
 * половины по отдельности останутся «правильными».
 *
 * Тест читает исходники, а не мокает fetch: проверять надо согласованность
 * двух половин, а не поведение одной из них.
 */

const repoRoot = fileURLToPath(new URL("../../../", import.meta.url));
const read = (p) => readFileSync(repoRoot + p, "utf-8");

const BACKEND = "backend/auth/rate_limits.py";
const FRONTEND = "frontend/src/components/TransitTimeline.jsx";

/** Значение FREE_TRANSITS_TEASER_MONTHS из rate_limits.py. */
function backendTeaserMonths() {
  const m = read(BACKEND).match(/^FREE_TRANSITS_TEASER_MONTHS\s*=\s*(\d+)/m);
  expect(m, `в ${BACKEND} не найдена FREE_TRANSITS_TEASER_MONTHS`).not.toBeNull();
  return Number(m[1]);
}

/** Литерал из `const maxMonths = isFree ? 12 : ...` в TransitTimeline.jsx. */
function frontendFreeMonths() {
  const m = read(FRONTEND).match(/const\s+maxMonths\s*=\s*isFree\s*\?\s*(\d+)\s*:/);
  expect(m, `в ${FRONTEND} не найдено "const maxMonths = isFree ? <число> :"`).not.toBeNull();
  return Number(m[1]);
}

describe("витрина транзитов free: фронтенд и бэкенд считают одинаково", () => {
  it("FREE_TRANSITS_TEASER_MONTHS совпадает с литералом в TransitTimeline", () => {
    expect(frontendFreeMonths()).toBe(backendTeaserMonths());
  });

  it("величина не нулевая — иначе витрины у free нет вовсе", () => {
    expect(backendTeaserMonths()).toBeGreaterThan(0);
  });

  it("на бэкенде это отдельная константа, а не transits_months у free", () => {
    // Если кто-то «починит» странность «free видит дальше Лиры», приравняв
    // витрину к тарифному флагу, free получит 0 и потеряет список транзитов.
    const src = read(BACKEND);
    expect(src).toMatch(/^FREE_TRANSITS_TEASER_MONTHS\s*=\s*\d+/m);
    expect(src).toContain("def transits_horizon_months");
  });
});
