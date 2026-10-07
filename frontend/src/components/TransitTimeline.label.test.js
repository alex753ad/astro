import { describe, it, expect } from "vitest";
import { transitLabel } from "./TransitTimeline";

// Шаг 9: подпись транзита на вебе — та же, что у ленты (feed/templates.json).
const ev = (transit_planet, natal_planet, aspect_type) => ({ transit_planet, natal_planet, aspect_type });

describe("transitLabel", () => {
  it("без флага — прежняя подпись", () => {
    expect(transitLabel(ev("Uranus", "Mercury", "conjunction"))).toBe("Уран Соединение Меркурий");
  });
  it("под sky_event — тон с маленькой буквы, к своей точке — «твой»", () => {
    expect(transitLabel(ev("Saturn", "Venus", "square"), true)).toBe("Сатурн и Венера: напряжение");
    expect(transitLabel(ev("Jupiter", "Sun", "trine"), true)).toBe("Юпитер и Солнце: гармония");
    expect(transitLabel(ev("Mars", "Sun", "conjunction"), true)).toBe("Марс и Солнце: соединение");
    expect(transitLabel(ev("Saturn", "Saturn", "square"), true)).toBe("Сатурн и твой Сатурн: напряжение");
    expect(transitLabel(ev("Moon", "Moon", "trine"), true)).toBe("Луна и твоя Луна: гармония");
  });
});
