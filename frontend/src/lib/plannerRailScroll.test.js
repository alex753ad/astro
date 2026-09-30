import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { planetCardTarget } from "./plannerDates";

/**
 * Прокрутка из подписи «Ближайших 30 дней» к карточке планеты (веб-планер).
 *
 * Её уже теряли: 7538cd0 (29.09.2026) переделал рельс в список и обратно,
 * а обработчик goToPlanet пропал по дороге — сборка и тесты были зелёными.
 * Поэтому, кроме выбора вкладки, здесь проверяется и ПРОВОДКА в странице:
 * jsdom в проекте нет, проводку держим чтением исходника, как в
 * plannerWeeks.test.js.
 */

const plan = {
  month_sections: [{ planet: "sun" }, { planet: "mars" }],
  longterm: [{ planet: "saturn" }],
};

describe("planetCardTarget", () => {
  it("карточка на текущей вкладке — вкладку не переключаем", () => {
    expect(planetCardTarget(plan, "sun", "month")).toEqual({ tab: "month", id: "plan-sec-sun" });
    expect(planetCardTarget(plan, "saturn", "longterm")).toEqual({ tab: "longterm", id: "plan-lt-saturn" });
  });

  it("карточки на текущей вкладке нет — ведём на ту, где она есть", () => {
    expect(planetCardTarget(plan, "saturn", "month")).toEqual({ tab: "longterm", id: "plan-lt-saturn" });
    expect(planetCardTarget(plan, "sun", "longterm")).toEqual({ tab: "month", id: "plan-sec-sun" });
    expect(planetCardTarget(plan, "mars", "week")).toEqual({ tab: "month", id: "plan-sec-mars" });
  });

  it("карточки нет нигде или события без планеты — null", () => {
    expect(planetCardTarget(plan, "pluto", "month")).toBeNull();
    expect(planetCardTarget(plan, undefined, "month")).toBeNull();
    expect(planetCardTarget(null, "sun", "month")).toBeNull();
  });
});

describe("проводка в PlannerPage.jsx", () => {
  const src = readFileSync(
    fileURLToPath(new URL("../pages/PlannerPage.jsx", import.meta.url)), "utf-8");

  it("рельс получает обработчик, подпись его вызывает", () => {
    expect(src).toMatch(/<Upcoming events=\{upcoming\} onPlanet=\{goToPlanet\} \/>/);
    expect(src).toMatch(/onPlanet\(ev\.planet\)/);
  });

  it("goToPlanet выбирает вкладку, переключает её и прокручивает", () => {
    const fn = src.slice(src.indexOf("function goToPlanet"));
    expect(fn).toMatch(/planetCardTarget\(planData, planet, tab\)/);
    expect(fn).toMatch(/setTab\(target\.tab\)/);
    expect(fn).toMatch(/getElementById\(target\.id\)\?\.scrollIntoView/);
  });

  it("id карточек совпадают с тем, что возвращает planetCardTarget", () => {
    expect(src).toContain("id={`plan-sec-${section.planet}`}");
    expect(src).toContain("id={`plan-lt-${lt.planet}`}");
  });
});
