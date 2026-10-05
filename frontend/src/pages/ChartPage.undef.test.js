// Необъявленные имена во вкладке транзитов (05.10.2026).
//
// 28.09.2026 (3bae9b7) удалили состояние showPaywall вместе со старым
// окном оплаты, а обёртка вкладки транзитов продолжала его читать. Сборка
// такое пропускает (имя — просто глобальная переменная), а на открытии
// вкладки ReferenceError ронял страницу в белый экран. Рендер-теста здесь нет
// (jsdom в проекте нет), поэтому проверка статическая — то же, что no-undef.
import { describe, expect, test } from "vitest";
import { readFileSync } from "node:fs";
import { parseSync, traverse } from "@babel/core";
import browserUpper from "@babel/helper-globals/data/browser-upper.json";

const BROWSER = new Set([
  ...browserUpper,
  "window", "document", "navigator", "location", "localStorage", "sessionStorage",
  "fetch", "alert", "confirm", "requestAnimationFrame", "cancelAnimationFrame",
  "getComputedStyle", "matchMedia", "atob", "btoa", "performance",
]);

function undefinedNames(file) {
  const ast = parseSync(readFileSync(new URL(file, import.meta.url), "utf8"), {
    filename: file, babelrc: false, configFile: false,
    parserOpts: { sourceType: "module", plugins: ["jsx"] },
  });
  const out = new Set();
  traverse(ast, {
    ReferencedIdentifier(path) {
      const { name } = path.node;
      if (path.isJSXIdentifier() && /^[a-z]/.test(name)) return; // <div>, <main>
      if (!path.scope.hasBinding(name, true) && !(name in globalThis) && !BROWSER.has(name)) out.add(name);
    },
  });
  return [...out];
}

describe("вкладка транзитов без необъявленных имён", () => {
  test.each(["./ChartPage.jsx", "../components/TransitTimeline.jsx"])("%s", (file) => {
    expect(undefinedNames(file)).toEqual([]);
  });
});
