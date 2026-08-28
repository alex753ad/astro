import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

/**
 * Контракт ответа POST /api/v1/payments/checkout.
 *
 * Зачем этот тест существует. Бэкенд отдаёт {checkout_url, payment_id}, а
 * четыре из пяти мест во фронтенде читали `const { url } = ...` — форму ответа
 * Stripe Checkout Session, провайдера, удалённого 19.08.2026. Значение было
 * undefined, `window.location.href = undefined` уводил браузер на /undefined,
 * nginx отдавал index.html с кодом 200, React не находил маршрут — пустая
 * страница. Исключения при этом не возникало, поэтому catch не срабатывал и
 * пользователь не видел даже сообщения об ошибке. Оплатить можно было только
 * из вкладки «Подписка» в профиле (единственное место, читавшее правильно).
 *
 * Обычный юнит-тест на createCheckoutSession этого бы не поймал: сама функция
 * была исправна, ломались её потребители. Поэтому тест сверяет две стороны
 * контракта по исходникам — имя поля в бэкенде и имя поля, которое читает
 * каждый вызывающий. При следующей смене платёжного провайдера (форма ответа
 * у всех своя: Stripe — `url`, ЮKassa — `confirmation.confirmation_url`)
 * расхождение выстрелит здесь, а не на живом пользователе.
 *
 * Тест намеренно читает файлы, а не мокает fetch: проверять надо именно
 * согласованность двух половин, а не поведение одной из них.
 */

const repoRoot = fileURLToPath(new URL("../../../", import.meta.url));
const read = (p) => readFileSync(repoRoot + p, "utf-8");

const BACKEND_ROUTER = "backend/payments/yookassa_router.py";

// Места, которые получают ссылку через createCheckoutSession() из api/client.js
const CLIENT_CALLERS = [
  "frontend/src/components/PaywallModal.jsx",
  "frontend/src/components/TransitTimeline.jsx",
  "frontend/src/pages/ChartPage.jsx",
  "frontend/src/pages/PlannerPage.jsx",
];

// ProfilePage ходит в эндпоинт напрямую через authFetch, минуя client.js —
// поэтому проверяется отдельно. Именно он единственный работал всё это время.
const DIRECT_CALLER = "frontend/src/pages/ProfilePage.jsx";

/** Ключи из `return {"a": ..., "b": ...}` в конце create_checkout. */
function checkoutResponseKeys() {
  const src = read(BACKEND_ROUTER);
  const fn = src.indexOf("async def create_checkout(");
  expect(fn, `в ${BACKEND_ROUTER} не найден create_checkout`).toBeGreaterThan(-1);

  // Последний return в теле функции — до следующего декоратора верхнего уровня.
  const nextRoute = src.indexOf("\n@router.", fn);
  const body = src.slice(fn, nextRoute === -1 ? undefined : nextRoute);
  const ret = body.match(/return\s*\{([^}]*)\}/);
  expect(ret, `в create_checkout не найден return {...}`).not.toBeNull();

  return [...ret[1].matchAll(/"([a-z_]+)"\s*:/g)].map((m) => m[1]);
}

describe("контракт POST /payments/checkout", () => {
  it("бэкенд отдаёт ссылку в поле checkout_url", () => {
    expect(checkoutResponseKeys()).toContain("checkout_url");
  });

  it.each(CLIENT_CALLERS)("%s читает checkout_url из ответа", (path) => {
    const src = read(path);
    const call = src.match(/const\s*\{([^}]*)\}\s*=\s*await\s+createCheckoutSession\(/);
    expect(call, `в ${path} не найден вызов createCheckoutSession с деструктуризацией`).not.toBeNull();
    expect(call[1]).toContain("checkout_url");
  });

  it.each(CLIENT_CALLERS)("%s не читает поле url (форма ответа Stripe)", (path) => {
    const src = read(path);
    // Ровно тот дефект, ради которого написан файл: `const { url } = await createCheckoutSession(`
    expect(src).not.toMatch(/const\s*\{\s*url\s*[,}][^=]*=\s*await\s+createCheckoutSession\(/);
  });

  it(`${DIRECT_CALLER} читает checkout_url из прямого ответа эндпоинта`, () => {
    expect(read(DIRECT_CALLER)).toContain("data.checkout_url");
  });

  it("ни одно поле ответа не потеряно: клиент знает про все ключи бэкенда", () => {
    // payment_id клиент не использует — это нормально, он для логов и поддержки.
    // Тест фиксирует состав ответа, чтобы добавление обязательного поля
    // (например confirmation_token для встроенного виджета) не прошло молча.
    expect(checkoutResponseKeys().sort()).toEqual(["checkout_url", "payment_id"]);
  });
});
