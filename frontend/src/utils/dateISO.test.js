import { describe, it, expect } from "vitest";
import { addDaysISO, addMonthISO, subMonthISO, monthEndISO } from "./dateISO";

// Обязательно прогонять под TZ=UTC И TZ=Europe/Moscow (см. package.json
// "test") — под UTC регрессия неподвижной точки не воспроизводится вообще,
// именно поэтому баг дожил до прода.

describe("addDaysISO", () => {
  it("advances a regular day by one", () => {
    expect(addDaysISO("2026-08-10", 1)).toBe("2026-08-11");
  });

  it("is not a fixed point — d must actually change (регресс 78da87f)", () => {
    const d = "2026-08-10";
    expect(addDaysISO(d, 1)).not.toBe(d);
  });

  it("repeated application never gets stuck (infinite-loop guard)", () => {
    let d = "2026-08-10";
    const seen = new Set();
    for (let i = 0; i < 10; i++) {
      d = addDaysISO(d, 1);
      expect(seen.has(d)).toBe(false);
      seen.add(d);
    }
  });

  it("crosses month and year boundaries", () => {
    expect(addDaysISO("2026-08-31", 1)).toBe("2026-09-01");
    expect(addDaysISO("2026-12-31", 1)).toBe("2027-01-01");
  });

  it("handles negative days", () => {
    expect(addDaysISO("2026-03-01", -1)).toBe("2026-02-28");
  });
});

describe("addMonthISO / subMonthISO", () => {
  it("regular day, no overflow", () => {
    expect(addMonthISO("2026-08-10")).toBe("2026-09-10");
    expect(subMonthISO("2026-08-10")).toBe("2026-07-10");
  });

  it("2026-01-31 + 1 month clamps to last day of February (not 2026-03-03)", () => {
    expect(addMonthISO("2026-01-31")).toBe("2026-02-28");
  });

  it("2026-03-31 clamps both directions", () => {
    expect(addMonthISO("2026-03-31")).toBe("2026-04-30");
    expect(subMonthISO("2026-03-31")).toBe("2026-02-28");
  });

  it("2026-12-31 + 1 month crosses the year boundary", () => {
    expect(addMonthISO("2026-12-31")).toBe("2027-01-31");
  });

  it("2028-02-29 (leap day) shifts correctly in both directions", () => {
    expect(addMonthISO("2028-02-29")).toBe("2028-03-29");
    expect(subMonthISO("2028-02-29")).toBe("2028-01-29");
  });
});

describe("monthEndISO", () => {
  it("offset 0 — last day of the same month", () => {
    expect(monthEndISO("2026-08-11", 0)).toBe("2026-08-31");
  });

  it("offset 2 — last day two months ahead (Pro/Lite horizon)", () => {
    expect(monthEndISO("2026-08-11", 2)).toBe("2026-10-31");
  });

  it("offset 12 crosses the year boundary (Free horizon)", () => {
    expect(monthEndISO("2026-08-11", 12)).toBe("2027-08-31");
  });

  it("offset 24 crosses multiple years (Premium horizon)", () => {
    expect(monthEndISO("2026-08-11", 24)).toBe("2028-08-31");
  });

  it("lands on a leap February", () => {
    expect(monthEndISO("2028-01-15", 1)).toBe("2028-02-29");
  });
});
