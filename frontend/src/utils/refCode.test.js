import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { captureRefCode, getRefCode } from "./refCode";

// Проект не тянет jsdom (тесты — чистый Node, см. dateISO.test.js), а
// localStorage в глобале Node нет — минимальный in-memory стаб вместо
// новой зависимости на весь проект ради одного файла.
if (typeof globalThis.localStorage === "undefined") {
  class MemoryStorage {
    constructor() { this.store = new Map(); }
    getItem(k) { return this.store.has(k) ? this.store.get(k) : null; }
    setItem(k, v) { this.store.set(k, String(v)); }
    removeItem(k) { this.store.delete(k); }
    clear() { this.store.clear(); }
  }
  globalThis.localStorage = new MemoryStorage();
}

const KEY = "astro_ref_code";
const ACCESS_TOKEN_KEY = "astro_access_token";

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("captureRefCode", () => {
  it("stores the code from ?ref=", () => {
    captureRefCode("?ref=polunina");
    expect(getRefCode()).toBe("polunina");
  });

  it("does nothing when there is no ref param", () => {
    captureRefCode("?utm_source=telegram");
    expect(getRefCode()).toBeNull();
  });

  it("does not overwrite when the visitor is already logged in", () => {
    localStorage.setItem(KEY, JSON.stringify({ code: "old", expiresAt: Date.now() + 1000 }));
    localStorage.setItem(ACCESS_TOKEN_KEY, "some-token");
    captureRefCode("?ref=someone-else");
    expect(getRefCode()).toBe("old");
  });

  it("overwrites a previously stored code for an anonymous visitor (last-touch before signup)", () => {
    captureRefCode("?ref=first");
    captureRefCode("?ref=second");
    expect(getRefCode()).toBe("second");
  });
});

describe("getRefCode", () => {
  it("returns null when nothing stored", () => {
    expect(getRefCode()).toBeNull();
  });

  it("returns null and clears storage past the 90-day TTL", () => {
    localStorage.setItem(KEY, JSON.stringify({ code: "polunina", expiresAt: Date.now() - 1 }));
    expect(getRefCode()).toBeNull();
    expect(localStorage.getItem(KEY)).toBeNull();
  });

  it("survives up to 89 days later", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-08-13T00:00:00Z"));
    captureRefCode("?ref=polunina");
    vi.setSystemTime(new Date("2026-08-13T00:00:00Z").getTime() + 89 * 24 * 60 * 60 * 1000);
    expect(getRefCode()).toBe("polunina");
  });

  it("expires at exactly 90 days", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-08-13T00:00:00Z"));
    captureRefCode("?ref=polunina");
    vi.setSystemTime(new Date("2026-08-13T00:00:00Z").getTime() + 90 * 24 * 60 * 60 * 1000 + 1);
    expect(getRefCode()).toBeNull();
  });

  it("returns null on corrupted JSON instead of throwing", () => {
    localStorage.setItem(KEY, "not-json");
    expect(getRefCode()).toBeNull();
  });
});
