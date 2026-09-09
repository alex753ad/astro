/**
 * tierSource.test.js — один источник тарифа и что показывать, пока он неизвестен.
 *
 * Разбор 09.09.2026. Источников было два: «Ещё» читало живой
 * `GET /profile/subscription`, а экран разбора — `user.tier` из `useAuth`,
 * куда тариф попадает только с обновлением токена. Пока токен жив (15 минут),
 * смена тарифа на сервере до экрана разбора не доезжала, и человеку на Лире
 * показывали приписку ветки free — предлагали купить Вегу тому, у кого уже
 * Лира. Приёмка поймала расхождение в одну минуту между двумя вкладками.
 *
 * ⚠️ Главный кейс здесь — `test_pro_user_does_not_see_free_upsell...`: тариф
 * изменился на сервере, токен ещё жив. До правки экран брал устаревший
 * `user.tier` и показывал приписку free; теперь тариф берётся из общего
 * источника, а до ответа не показывается ничего.
 *
 * ⚠️ Второе, что стерегут эти тесты, — отсутствие залпа. `TabShell` монтирует
 * три экрана разом, и залп уже был причиной гейта по сроку токена (CLAUDE.md,
 * «Холодный старт упирается в ЗАДЕРЖИВАЮЩИЙ лимит»). Поэтому проверяется, что
 * N потребителей дают ОДИН запрос, а не N.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Транспорт подменяется целиком: настоящий moreApi тянет api/client.js, а тот
// @capacitor/preferences, которого в тестовой среде нет. Тот же приём и та же
// причина, что в api/session.test.js.
let calls = 0;
let respond = () => Promise.resolve({ tier: "pro", features: { rag_chat: true } });

vi.mock("./moreApi", () => ({
  fetchSubscription: () => {
    calls += 1;
    return respond();
  },
}));

const { getSubscription, onSubscription, peekSubscription, resetSubscription } =
  await import("./tierSource");
const { upsellForTier } = await import("./interpretRules");

beforeEach(() => {
  calls = 0;
  respond = () => Promise.resolve({ tier: "pro", features: { rag_chat: true } });
  resetSubscription();
});

afterEach(() => resetSubscription());

describe("тариф pro на сервере, токен ещё жив", () => {
  it("приписка ветки free НЕ показывается — главный кейс", async () => {
    // До правки экран читал user.tier из useAuth. Там лежал устаревший
    // 'free' (тариф сменили, а токен ещё не обновлялся), и человек на Лире
    // видел «На тарифе Вега интерпретация примерно на 800 слов».
    const sub = await getSubscription();
    const shown = upsellForTier({
      tier: sub.tier, known: true, finished: true, failed: false,
    });
    expect(shown).toBeNull();
  });

  it("до ответа сервера не показывается НИЧЕГО, а не ветка free", async () => {
    // Незнание — не бесплатный тариф. interpretationUpsell(undefined) отдаёт
    // ветку free, и именно так платящему предлагали то, что у него есть.
    expect(peekSubscription()).toBeNull();
    const shown = upsellForTier({
      tier: null, known: false, finished: true, failed: false,
    });
    expect(shown).toBeNull();
  });

  it("устаревший free из другого источника не может просочиться", async () => {
    // Даже если где-то ещё лежит 'free', решение принимается по known/tier
    // из общего источника — иначе второй источник вернулся бы незаметно.
    const shown = upsellForTier({
      tier: "free", known: false, finished: true, failed: false,
    });
    expect(shown).toBeNull();
  });
});

describe("free действительно free — приписка на месте", () => {
  it("подтверждённый free получает предложение Веги", async () => {
    respond = () => Promise.resolve({ tier: "free", features: {} });
    const sub = await getSubscription();
    const shown = upsellForTier({
      tier: sub.tier, known: true, finished: true, failed: false,
    });
    expect(shown.kind).toBe("free");
    expect(shown.text).toContain("Вега");
  });

  it("подтверждённый lite получает баннер Лиры", async () => {
    respond = () => Promise.resolve({ tier: "lite", features: {} });
    const sub = await getSubscription();
    expect(upsellForTier({ tier: sub.tier, known: true, finished: true, failed: false }).kind)
      .toBe("lite");
  });

  it("незавершённый или упавший разбор приписки не получает", () => {
    const base = { tier: "free", known: true };
    expect(upsellForTier({ ...base, finished: false, failed: false })).toBeNull();
    expect(upsellForTier({ ...base, finished: true, failed: true })).toBeNull();
  });
});

describe("залпа нет: один запрос на всех потребителей", () => {
  it("три одновременных потребителя дают ОДИН запрос", async () => {
    // TabShell монтирует три экрана разом. До правки /profile/subscription
    // запрашивался дважды на холодном старте — из MoreScreen и useChatAccess,
    // каждый сам по себе.
    await Promise.all([getSubscription(), getSubscription(), getSubscription()]);
    expect(calls).toBe(1);
  });

  it("повторное открытие экрана запроса не делает", async () => {
    await getSubscription();
    await getSubscription();
    expect(calls).toBe(1);
  });

  it("жест обновления форсит — иначе человек тянет экран впустую", async () => {
    await getSubscription();
    await getSubscription({ force: true });
    expect(calls).toBe(2);
  });
});

describe("подписка и сброс", () => {
  it("подписчик получает уже готовый ответ сразу", async () => {
    await getSubscription();
    const seen = [];
    const off = onSubscription((d) => seen.push(d?.tier));
    expect(seen).toEqual(["pro"]);
    off();
  });

  it("выход из аккаунта стирает тариф — иначе следующий увидит чужой", async () => {
    await getSubscription();
    expect(peekSubscription().tier).toBe("pro");
    resetSubscription();
    expect(peekSubscription()).toBeNull();
  });

  it("после сброса запрос идёт заново", async () => {
    await getSubscription();
    resetSubscription();
    await getSubscription();
    expect(calls).toBe(2);
  });

  it("отписавшийся больше не получает обновлений", async () => {
    const seen = [];
    const off = onSubscription((d) => seen.push(d?.tier));
    off();
    await getSubscription();
    expect(seen).toEqual([]);
  });
});
