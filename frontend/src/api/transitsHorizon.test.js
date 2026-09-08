import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

/**
 * Синхронность витрины транзитов для free между фронтендом и бэкендом.
 *
 * Зачем этот тест существует. Горизонт списка транзитов у free живёт в двух
 * местах, в разных языках:
 *
 *   - `constants.js` — `FREE_TRANSITS_TEASER_MONTHS`, единственный источник на
 *     фронте с 03.09.2026: по нему считает `TransitTimeline` (для free он
 *     горизонт с сервера НЕ запрашивает вовсе, ветка `isFree`) и по нему же
 *     набирается строка витрины в `TIERS` у бесплатного тарифа;
 *   - `rate_limits.py` — `TIER_FLAGS["free"]["transits_months"]`, по которому
 *     сервер с 31.08.2026 отдаёт 403 за горизонтом.
 *
 * До 08.09.2026 серверной половиной была отдельная константа
 * `FREE_TRANSITS_TEASER_MONTHS`, а сам флаг стоял нулём — второй источник
 * истины внутри бэкенда. Он убран, флаг поднят до 3, и тест сверяет фронт
 * уже с флагом; проверка «на бэкенде это не константа рядом с флагом»
 * заменила прежнюю, требовавшую обратного.
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
const PROFILE = "frontend/src/pages/ProfilePage.jsx";

/** Значение TIER_FLAGS["free"]["transits_months"] из rate_limits.py. */
function backendFreeMonths() {
  const src = read(BACKEND);
  const free = src.slice(src.indexOf('"free": {'), src.indexOf('"lite": {'));
  const m = free.match(/"transits_months":\s*(\d+)/);
  expect(m, `в ${BACKEND} не найден transits_months у free`).not.toBeNull();
  return Number(m[1]);
}

/** Значение FREE_TRANSITS_TEASER_MONTHS из constants.js. */
function frontendFreeMonths() {
  const m = read(FRONTEND).match(/^export const FREE_TRANSITS_TEASER_MONTHS\s*=\s*(\d+)/m);
  expect(m, `в ${FRONTEND} не найдена FREE_TRANSITS_TEASER_MONTHS`).not.toBeNull();
  return Number(m[1]);
}

describe("витрина транзитов free: фронтенд и бэкенд считают одинаково", () => {
  it("константа фронта совпадает с transits_months у free на бэкенде", () => {
    expect(frontendFreeMonths()).toBe(backendFreeMonths());
  });

  it("величина не нулевая — иначе витрины у free нет вовсе", () => {
    expect(backendFreeMonths()).toBeGreaterThan(0);
  });

  it("TransitTimeline считает по константе, а не по своему литералу", () => {
    // Литерал здесь означал бы третью копию числа: константа, текст витрины и
    // расчёт горизонта разъехались бы молча, а увидел бы это только free —
    // получив 403 на странице, ради которой всё и показывается.
    const src = read(TIMELINE);
    expect(src).toMatch(/const\s+maxMonths\s*=\s*isFree\s*\?\s*FREE_TRANSITS_TEASER_MONTHS\s*:/);
    expect(src).not.toMatch(/const\s+maxMonths\s*=\s*isFree\s*\?\s*\d+\s*:/);
  });

  it("ProfilePage не обходит признак transits вручную для free", () => {
    // Обход существовал ровно потому, что сервер врал: transits приходил
    // false при живой витрине. Возврат обхода означал бы, что второй
    // источник истины на бэкенде вернулся — а увидеть это по самому
    // ProfilePage нельзя, там всё выглядит нарочито правильно.
    const src = read(PROFILE);
    expect(src).not.toMatch(/ok:\s*isFreeTier\s*\?/);
    expect(src).toContain("ok: !!feat.transits");
  });

  it("на бэкенде это сам флаг, а не константа рядом с ним", () => {
    // Обратная прежней проверке (см. шапку). Второй источник истины внутри
    // бэкенда уже приводил к тому, что сервер отдавал features.transits =
    // false при живой витрине, и фронтенду приходилось это обходить руками.
    const src = read(BACKEND);
    expect(src).not.toMatch(/^FREE_TRANSITS_TEASER_MONTHS\s*=/m);
    expect(src).toContain("def transits_horizon_months");
  });
});
