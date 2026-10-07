// Только no-undef: ловит необъявленные переменные, которые сборка Vite
// пропускает молча (3bae9b7, 28.09.2026 — неделя упавшей вкладки транзитов, #123).
// Остальные правила не включены намеренно — отдельное решение владельца.
import globals from "globals";
import reactHooks from "eslint-plugin-react-hooks";

export default [
  { ignores: ["dist/**", "dist-mobile/**", "android/**", "node_modules/**", "public/**", "!public/sw.js"] },
  {
    files: ["**/*.{js,jsx,mjs}"],
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
    // Плагин подключён без правил: в коде есть `eslint-disable react-hooks/...`,
    // без плагина eslint падает на них «Definition for rule … not found».
    plugins: { "react-hooks": reactHooks },
    rules: { "no-undef": "error" },
  },
  {
    files: ["src/**/*.{js,jsx}"],
    // __APP_RELEASE__ подставляет Vite (define в vite.config.mobile.js).
    languageOptions: { globals: { ...globals.browser, __APP_RELEASE__: "readonly" } },
  },
  {
    files: ["src/**/*.test.{js,jsx}", "src/**/__tests__/**"],
    // process — тесты vitest идут под node (process.env.TZ в yearBoundary.test.js).
    languageOptions: { globals: { ...globals.vitest, process: "readonly" } },
  },
  {
    files: ["public/sw.js"],
    languageOptions: { sourceType: "script", globals: { ...globals.serviceworker } },
  },
  {
    files: ["*.{js,mjs}", "scripts/**/*.mjs"],
    languageOptions: { globals: { ...globals.node } },
  },
  {
    // Функции prerender уходят в page.evaluate и выполняются в браузере.
    files: ["scripts/prerender.mjs"],
    languageOptions: { globals: { ...globals.node, ...globals.browser } },
  },
];
