import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { mergeUserFromTokens } from "./sessionUser";

/**
 * Тариф обязан становиться актуальным без повторного входа.
 *
 * Разбор 09.09.2026. `refreshSession` (`api/client.js`) писал только токены и
 * `astro_user` не трогал; его уведомление `onTokensRefreshed` не имело НИ
 * ОДНОГО подписчика, хотя ответ `/auth/refresh` содержит `tier`. Единственным
 * местом, где `user.tier` перезаписывался, оставался `applyTokenResponse` —
 * то есть вход. Смена тарифа на сервере доезжала до приложения только после
 * повторного логина.
 *
 * Наружу это выглядело как известный симптом «оплаченный тариф не применяется
 * до перезапуска приложения», который прежде объясняли зависанием объекта
 * плагина Capacitor. То зависание было настоящим и починено — но симптом
 * объясняло не оно.
 *
 * ⚠️ Проверяется и сама функция, и ФАКТ ПОДПИСКИ в useAuth. Хук без
 * DOM-окружения не смонтировать (его в проекте нет), а без подписки чистая
 * функция бесполезна: она будет правильной и никем не вызванной — ровно то
 * состояние, в котором `onTokensRefreshed` прожил до этой правки. Проверка
 * подписки грепом по исходнику — тот же приём, что в
 * `api/transitsHorizon.test.js`.
 */

const repoRoot = fileURLToPath(new URL("../../../", import.meta.url));
const read = (p) => readFileSync(repoRoot + p, "utf-8");

const USE_AUTH = "frontend/src/hooks/useAuth.jsx";
const CLIENT = "frontend/src/api/client.js";

const USER = {
  id: "u1",
  email: "a@b.ru",
  name: "Имя",
  tier: "free",
  is_admin: false,
  is_partner: false,
};

describe("mergeUserFromTokens — свежий тариф из ответа обновления", () => {
  it("тариф сменился на сервере — приезжает в user", () => {
    const next = mergeUserFromTokens(USER, { tier: "pro" });
    expect(next.tier).toBe("pro");
  });

  it("остальные поля не теряются", () => {
    const next = mergeUserFromTokens(USER, { tier: "pro" });
    expect(next.id).toBe("u1");
    expect(next.email).toBe("a@b.ru");
    expect(next.name).toBe("Имя");
  });

  it("ничего не изменилось — возвращается ТОТ ЖЕ объект", () => {
    // Сравнение по ссылке: иначе каждое обновление токена (раз в 13 минут)
    // перерисовывало бы всё дерево на ровном месте.
    const next = mergeUserFromTokens(USER, { tier: "free", email: "a@b.ru" });
    expect(next).toBe(USER);
  });

  it("отсутствующее поле не затирает известное", () => {
    // Ответы разных ручек различаются составом; undefined из одной не должен
    // стирать имя, пришедшее из другой.
    const next = mergeUserFromTokens(USER, { tier: "lite" });
    expect(next.name).toBe("Имя");
    expect(next.is_partner).toBe(false);
  });

  it("null тоже не затирает — сервер шлёт его вместо отсутствия", () => {
    const next = mergeUserFromTokens(USER, { tier: "lite", name: null });
    expect(next.name).toBe("Имя");
  });

  it("не вошли — пользователь не воскресает из ответа", () => {
    // Обновление может прийти, когда сессия уже погашена.
    expect(mergeUserFromTokens(null, { tier: "pro", user_id: "u9" })).toBeNull();
  });

  it("пустой ответ ничего не ломает", () => {
    expect(mergeUserFromTokens(USER, null)).toBe(USER);
    expect(mergeUserFromTokens(USER, {})).toBe(USER);
  });

  it("обновляются все поля, которые приезжают с токенами", () => {
    const next = mergeUserFromTokens(USER, {
      user_id: "u2", email: "c@d.ru", name: "Другое",
      tier: "premium", is_admin: true, is_partner: true,
    });
    expect(next).toEqual({
      id: "u2", email: "c@d.ru", name: "Другое",
      tier: "premium", is_admin: true, is_partner: true,
    });
  });
});

describe("подписка на обновление токенов существует", () => {
  it("useAuth подписан на onTokensRefreshed", () => {
    // До 09.09.2026 подписчиков не было ни одного, и уведомление уходило в
    // пустоту вместе со свежим тарифом.
    const src = read(USE_AUTH);
    expect(src).toContain("onTokensRefreshed");
    expect(src).toMatch(/onTokensRefreshed\(\s*\(/);
  });

  it("обработчик обновляет пользователя, а не только токен", () => {
    const src = read(USE_AUTH);
    expect(src).toContain("mergeUserFromTokens");
  });

  it("подписка не тянет за собой сетевой запрос", () => {
    // Тариф уже приехал в ответе обновления. Лишний запрос здесь удлинил бы
    // залп на холодном старте — тот самый, из-за которого писались гейт по
    // сроку токена и пауза после неудачного обновления.
    const src = read(USE_AUTH);
    const start = src.indexOf("onTokensRefreshed((data)");
    expect(start, "подписка не найдена").toBeGreaterThan(-1);
    const handler = src.slice(start, start + 400);
    expect(handler).not.toMatch(/fetch\(|authFetch\(|getSubscription\(|loadFeatures\(/);
  });

  it("client.js по-прежнему уведомляет — иначе подписка пуста", () => {
    const src = read(CLIENT);
    expect(src).toContain("notify(tokensRefreshedHandlers, data)");
  });
});
