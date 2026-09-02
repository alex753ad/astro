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
 *   - `constants.js` — `FREE_TRANSITS_TEASER_MONTHS`, единственный источник на
 *     фронте с 03.09.2026: по нему считает `TransitTimeline` и по нему же
 *     набирается строка витрины в `TIERS` у бесплатного тарифа;
 *   - `rate_limits.py` — `FREE_TRANSITS_TEASER_MONTHS`, по которому сервер с
 *     31.08.2026 отдаёт 403 за горизонтом.
 *
 * До 03.09.2026 фронтовая половина была ЛИТЕРАЛОМ в `TransitTimeline.jsx`, и
 * тест сверял именно его. Когда витрину понадобилось назвать ещё и в тексте
 * тарифа, литерал стал бы третьей копией — поэтому он вынесен в константу, а
 * тест переведён на неё и дополнен проверкой, что литерал не вернулся.
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
const FRONTEND = "frontend/src/constants.js";
const TIMELINE = "frontend/src/components/TransitTimeline.jsx";

/** Значение FREE_TRANSITS_TEASER_MONTHS из rate_limits.py. */
function backendTeaserMonths() {
  const m = read(BACKEND).match(/^FREE_TRANSITS_TEASER_MONTHS\s*=\s*(\d+)/m);
  expect(m, `в ${BACKEND} не найдена FREE_TRANSITS_TEASER_MONTHS`).not.toBeNull();
  return Number(m[1]);
}

/** Значение FREE_TRANSITS_TEASER_MONTHS из constants.js. */
function frontendFreeMonths() {
  const m = read(FRONTEND).match(/^export const FREE_TRANSITS_TEASER_MONTHS\s*=\s*(\d+)/m);
  expect(m, `в ${FRONTEND} не найдена FREE_TRANSITS_TEASER_MONTHS`).not.toBeNull();
  return Number(m[1]);
}

describe("витрина транзитов free: фронтенд и бэкенд считают одинаково", () => {
  it("FREE_TRANSITS_TEASER_MONTHS во фронте и на бэкенде совпадают", () => {
    expect(frontendFreeMonths()).toBe(backendTeaserMonths());
  });

  it("величина не нулевая — иначе витрины у free нет вовсе", () => {
    expect(backendTeaserMonths()).toBeGreaterThan(0);
  });

  it("TransitTimeline считает по константе, а не по своему литералу", () => {
    // Литерал здесь означал бы третью копию числа: константа, текст витрины и
    // расчёт горизонта разъехались бы молча, а увидел бы это только free —
    // получив 403 на странице, ради которой всё и показывается.
    const src = read(TIMELINE);
    expect(src).toMatch(/const\s+maxMonths\s*=\s*isFree\s*\?\s*FREE_TRANSITS_TEASER_MONTHS\s*:/);
    expect(src).not.toMatch(/const\s+maxMonths\s*=\s*isFree\s*\?\s*\d+\s*:/);
  });

  it("на бэкенде это отдельная константа, а не transits_months у free", () => {
    // Если кто-то «починит» странность «free видит дальше Лиры», приравняв
    // витрину к тарифному флагу, free получит 0 и потеряет список транзитов.
    const src = read(BACKEND);
    expect(src).toMatch(/^FREE_TRANSITS_TEASER_MONTHS\s*=\s*\d+/m);
    expect(src).toContain("def transits_horizon_months");
  });
});
