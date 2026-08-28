import { describe, it, expect, vi, afterEach } from "vitest";
import { responseErrorText, streamTransitEventInterpretation } from "./client";

/**
 * Отказ потокового POST-эндпоинта должен доезжать до пользователя.
 *
 * POST /chart/{id}/transits/event/interpret читается вручную через
 * resp.body.getReader(), мимо request() — значит ApiError не создаётся и
 * detail, если его не прочитать, просто пропадает. Так и было:
 * streamTransitEventInterpretation шла в getReader() без проверки resp.ok, на
 * 403 в теле лежал обычный JSON без строк `data: `, цикл не выдавал ни одного
 * события, доходил до done и вызывал onDone — отказ выглядел как успешно
 * завершившийся пустой разбор.
 *
 * Здесь, в отличие от EventSource, транспорт статус НЕ теряет: и resp.status, и
 * тело доступны JS. Поэтому лечение клиентское, а не переводом 403 в 200 на
 * бэкенде, как пришлось сделать для SSE-эндпоинтов.
 */

const okStream = (chunks) => ({
  ok: true,
  status: 200,
  body: {
    getReader() {
      let i = 0;
      return {
        read: async () =>
          i < chunks.length
            ? { done: false, value: new TextEncoder().encode(chunks[i++]) }
            : { done: true, value: undefined },
      };
    },
  },
});

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

describe("streamTransitEventInterpretation", () => {
  it("на 403 зовёт onError с текстом бэкенда, а не onDone", async () => {
    const detail = "AI-расшифровка транзитов доступна на Лире и выше.";
    vi.stubGlobal("fetch", async () => errorResponse(403, { detail }));

    const onChunk = vi.fn();
    const onDone = vi.fn();
    const onError = vi.fn();

    await streamTransitEventInterpretation("chart-1", {}, onChunk, onDone, onError);

    expect(onError).toHaveBeenCalledWith(detail);
    // Именно это и было сломано: отказ доходил как успех.
    expect(onDone).not.toHaveBeenCalled();
    expect(onChunk).not.toHaveBeenCalled();
  });

  it("на 200 по-прежнему стримит текст и завершается onDone", async () => {
    vi.stubGlobal("fetch", async () =>
      okStream([
        'data: {"text":"Первая часть. "}\n',
        'data: {"text":"Вторая часть."}\n',
        "data: [DONE]\n",
      ])
    );

    const chunks = [];
    const onDone = vi.fn();
    const onError = vi.fn();

    await streamTransitEventInterpretation(
      "chart-1", {}, (c) => chunks.push(c), onDone, onError
    );

    expect(chunks.join("")).toBe("Первая часть. Вторая часть.");
    expect(onDone).toHaveBeenCalled();
    expect(onError).not.toHaveBeenCalled();
  });

  it("ошибка внутри потока по-прежнему доходит через onError", async () => {
    vi.stubGlobal("fetch", async () =>
      okStream(['data: {"error":"Дневной лимит AI-запросов исчерпан."}\n'])
    );

    const onError = vi.fn();
    await streamTransitEventInterpretation("chart-1", {}, vi.fn(), vi.fn(), onError);

    expect(onError).toHaveBeenCalledWith("Дневной лимит AI-запросов исчерпан.");
  });
});
