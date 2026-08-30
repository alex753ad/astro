import { describe, it, expect, vi, afterEach } from "vitest";
import { responseErrorText } from "./client";

const errorResponse = (status, body) => ({
  ok: false,
  status,
  json: async () => {
    if (body === undefined) throw new SyntaxError("Unexpected end of JSON input");
    return body;
  },
  body: {
    getReader() {
      throw new Error("getReader не должен вызываться при !ok");
    },
  },
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("responseErrorText", () => {
  it("отдаёт detail, когда он строка", async () => {
    const text = await responseErrorText(
      errorResponse(403, { detail: "AI-расшифровка транзитов доступна на Лире и выше." })
    );
    expect(text).toBe("AI-расшифровка транзитов доступна на Лире и выше.");
  });

  it("не показывает detail-объект — там нечего читать человеку", async () => {
    // Часть эндпоинтов отдаёт {error: "tier_required", required: "pro"}
    const text = await responseErrorText(
      errorResponse(403, { detail: { error: "tier_required", required: "pro" } }),
      "Нет доступа."
    );
    expect(text).toBe("Нет доступа. (403)");
  });

  it("переживает нечитаемое тело", async () => {
    const text = await responseErrorText(errorResponse(502, undefined), "Сервис недоступен.");
    expect(text).toBe("Сервис недоступен. (502)");
  });

  it("пустой detail не выдаётся за объяснение", async () => {
    const text = await responseErrorText(errorResponse(429, { detail: "   " }), "Позже.");
    expect(text).toBe("Позже. (429)");
  });
});
